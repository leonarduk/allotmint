"""Short factual explanations of unmatched contributions (#10491).

The matcher (:mod:`backend.allowance_guardian.match`) gives each expected
contribution a status. For the ones that are ``missing``, ``wrong_amount`` or
``late``, :func:`explain_unmatched` asks the configured chat provider for one
sentence on what the records show, for example that a payment of the same
amount arrived after the window, or that two payments in the window add up to
less than expected.

Guardrails, all checked here rather than trusted:

* the model runs through :func:`backend.chat.providers.run_configured_chat_turn`
  (Bedrock or an OpenAI-compatible provider, whichever is configured) with a
  :class:`backend.chat.turn_limits.TurnLimits` that offers, and allows, only
  :data:`READ_ONLY_TOOLS`;
* each explanation must pass the guardian's no-advice wording check
  (:mod:`backend.common.advice_wording`) and quote no £ amount that is not in
  the facts given or in a tool result from this run; otherwise it is dropped
  and the entry carries a note saying why;
* any provider failure leaves every entry without an explanation, with a note.

Read-only and opt-in: :func:`backend.allowance_guardian.report.run` calls this
only when asked (``explain=True``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Mapping, Optional, Sequence

from backend.allowance_guardian.match import AMOUNT_TOLERANCE_MINOR, EARLY_DAYS, LATE_WINDOW_DAYS, ON_TIME_GRACE_DAYS
from backend.chat.tool_switches import is_read_only_tool_name
from backend.chat.turn_limits import TurnLimits
from backend.common.advice_wording import advice_phrases
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

#: The only tools the explainer is offered or allowed to call. Every one only reads;
#: ``tests/backend/allowance_guardian/test_agent.py`` checks the exact set.
READ_ONLY_TOOLS: frozenset[str] = frozenset({"get_transactions", "summarise_transactions", "get_pension_forecast"})
if not all(is_read_only_tool_name(name) for name in READ_ONLY_TOOLS):
    raise RuntimeError("Allowance guardian explainer tool allowlist must contain read-only tools only")

#: Statuses that get an explanation, in the order the report counts them.
EXPLAINED_STATUSES = ("missing", "wrong_amount", "late")
MAX_TOOL_CALL_ROUNDS = 4
MAX_OUTPUT_TOKENS = 1500
MAX_EXPLANATION_CHARS = 400
#: Unmatched deposits within this many days of an expected date are listed as facts for it.
NEARBY_DAYS = 60

NOTE_NOT_CONFIGURED = "Explanations are not configured on this server (no MCP server URL)."
NOTE_FAILED = "The explanation model failed; no explanation is shown."
NOTE_NO_REPLY = "The model gave no explanation for this contribution."
NOTE_ADVICE = "The model's explanation was removed: its wording read as advice."
NOTE_FIGURES = "The model's explanation was removed: it quoted an amount not found in the records."

SYSTEM_PROMPT = (
    "You explain, in one or two short sentences each, why scheduled pension or ISA contributions did not "
    "match the owner's recorded deposits. State only what the records show: dates, amounts, and how they "
    "differ from what was expected. Use the facts given; you may call the tools offered to look at the "
    "owner's transactions. Quote amounts exactly as they appear in the facts or tool results and invent "
    "none. Describe what happened only. Never tell the owner what to do, and never mention amounts to pay, "
    "allowances, carry-forward or tax. Reply with JSON only: "
    '{"explanations": [{"id": <the number in square brackets>, "explanation": "<text>"}]}.'
)

ChatTurn = Callable[..., Coroutine[Any, Any, str]]

_MONEY_RE = re.compile(r"£\s?(\d[\d,]*(?:\.\d+)?)")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_STATUS_WORDS = {"missing": "missing", "wrong_amount": "a different amount", "late": "late"}


def _gbp(minor: int) -> str:
    return f"£{minor / 100:,.2f}"


def needs_explanation(report: Mapping[str, Any]) -> bool:
    """True when the report counts any missing, wrong-amount or late contribution."""
    counts = (report.get("contributions") or {}).get("counts") or {}
    return any(counts.get(status) for status in EXPLAINED_STATUSES)


def unmatched_results(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The report's contribution results that get an explanation, in expected-date order."""
    results = (report.get("contributions") or {}).get("results") or []
    return [row for row in results if row.get("status") in EXPLAINED_STATUSES]


def _rows_text(rows: Sequence[Mapping[str, Any]]) -> str:
    return ", ".join(f"{row['date']} {_gbp(row['amount_minor'])}" for row in rows)


def _window_deposits(row: Mapping[str, Any], unmatched: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """The row's matched deposits plus unmatched ones in the same account inside its matching window."""
    due = date.fromisoformat(row["expected_date"])
    start, end = due - timedelta(days=EARLY_DAYS), due + timedelta(days=LATE_WINDOW_DAYS)
    in_window = [
        dep
        for dep in unmatched
        if dep["account"] == str(row["account"]).lower() and start <= date.fromisoformat(dep["date"]) <= end
    ]
    return sorted([*(row.get("matched_rows") or []), *in_window], key=lambda dep: dep["date"])


def _difference(received: int, expected: int) -> str:
    diff = received - expected
    return f"{_gbp(abs(diff))} {'more' if diff > 0 else 'less'} than expected"


def _status_line(row: Mapping[str, Any], unmatched: Sequence[Mapping[str, Any]]) -> str:
    rows = row.get("matched_rows") or []
    if row["status"] == "missing":
        return "No eligible deposit was recorded in the matching window."
    if row["status"] == "late":
        return f"Paid by {_rows_text(rows)}; the last arrived {row['days_late']} days after the expected date."
    window = _window_deposits(row, unmatched)
    total = sum(int(dep["amount_minor"]) for dep in window)
    return (
        f"Nearest deposit in the window: {_rows_text(rows)}, "
        f"{_difference(row['received_amount_minor'], row['expected_amount_minor'])}. "
        f"All deposits recorded in this account in the window: {_rows_text(window)}; together {_gbp(total)}, "
        f"{_difference(total, row['expected_amount_minor'])}."
    )


def _nearby_lines(row: Mapping[str, Any], unmatched: Sequence[Mapping[str, Any]]) -> List[str]:
    due = date.fromisoformat(row["expected_date"])
    lines = []
    for dep in unmatched:
        offset = (date.fromisoformat(dep["date"]) - due).days
        if dep["account"] != str(row["account"]).lower() or abs(offset) > NEARBY_DAYS:
            continue
        when = "on" if offset == 0 else f"{abs(offset)} days {'after' if offset > 0 else 'before'}"
        lines.append(
            f"  Unmatched deposit in this account: {dep['date']} {_gbp(dep['amount_minor'])} "
            f"({when} the expected date)."
        )
    return lines


def render_facts(report: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    """The unmatched contributions and the matcher's rules as plain sentences for the model."""
    unmatched = (report.get("contributions") or {}).get("unmatched_deposits") or []
    lines = [
        f"Matching rules: a deposit matches when it arrives between {EARLY_DAYS} days before and "
        f"{LATE_WINDOW_DAYS} days after the expected date and is within {_gbp(AMOUNT_TOLERANCE_MINOR)} of "
        f"the expected amount (several deposits in the window may add up to it). It is on time when paid at "
        f"most {ON_TIME_GRACE_DAYS} days after the expected date, otherwise late. Relief-at-source top-ups, "
        "transfers, refunds and reversals are never matched.",
    ]
    for index, row in enumerate(rows):
        label = f", {row['label']}" if row.get("label") else ""
        lines.append(
            f"[{index}] Account {row['account']} ({row['source']}{label}), expected {row['expected_date']}: "
            f"{_gbp(row['expected_amount_minor'])}. Status: {_STATUS_WORDS[row['status']]}. "
            f"{_status_line(row, unmatched)}"
        )
        lines.extend(_nearby_lines(row, unmatched))
    return "\n".join(lines)


def build_user_message(report: Mapping[str, Any], owner: str, facts: str) -> str:
    return (
        f"Owner: {owner}. Tax year {report.get('tax_year')}, as of {report.get('as_of')}.\n"
        f"Unmatched contributions:\n{facts}"
    )


def _extract_json(reply: str) -> Optional[Dict[str, Any]]:
    """The first JSON object in ``reply`` (models sometimes wrap it in a code fence or prose)."""
    text = re.sub(r"```(?:json)?", "", reply or "")
    start = text.find("{")
    while start != -1:
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        return value if isinstance(value, dict) else None
    return None


def _known_amounts(facts: str, limits: TurnLimits) -> set[float]:
    """Amounts the reply may quote: every number in the facts or a tool result, as pounds or as pence."""
    sources = [facts] + [str(call.get("result") or "") for call in limits.tool_log if not call.get("is_error")]
    numbers = {float(raw.replace(",", "")) for text in sources for raw in _NUMBER_RE.findall(text)}
    pounds = numbers | {value / 100 for value in numbers}
    return {round(value, 2) for value in pounds} | {float(round(value)) for value in pounds}


def unsupported_amounts(text: str, known: set[float]) -> List[float]:
    """£ amounts in ``text`` that are not in ``known``."""
    quoted = [round(float(raw.replace(",", "")), 2) for raw in _MONEY_RE.findall(text) if raw.strip(".,")]
    return sorted(value for value in quoted if value not in known)


def _entry(row: Mapping[str, Any], explanation: Optional[str], note: Optional[str]) -> Dict[str, Any]:
    return {
        "expected_date": row["expected_date"],
        "account": row["account"],
        "status": row["status"],
        "explanation": explanation,
        "note": note,
    }


def _checked(text: Any, known: set[float]) -> tuple[Optional[str], Optional[str]]:
    """(explanation, note): the explanation when it passes every check, else None and the reason."""
    explanation = str(text or "").strip()
    if not explanation:
        return None, NOTE_NO_REPLY
    if advice_phrases(explanation):
        return None, NOTE_ADVICE
    if unsupported_amounts(explanation, known):
        return None, NOTE_FIGURES
    return explanation[:MAX_EXPLANATION_CHARS], None


def interpret_reply(
    rows: Sequence[Mapping[str, Any]], reply: str, facts: str, limits: TurnLimits
) -> List[Dict[str, Any]]:
    """One entry per row in ``rows``; an explanation is kept only if it passes the checks."""
    parsed = _extract_json(reply) or {}
    raw_items = parsed.get("explanations")
    by_id: Dict[int, Any] = {}
    for item in raw_items if isinstance(raw_items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            by_id.setdefault(item["id"], item.get("explanation"))
    known = _known_amounts(facts, limits)
    entries = []
    for index, row in enumerate(rows):
        explanation, note = _checked(by_id.get(index), known)
        if note in (NOTE_ADVICE, NOTE_FIGURES):
            logger.warning(
                "Allowance guardian explanation [%s] rejected: %s", sanitise_log_value(index), sanitise_log_value(note)
            )
        entries.append(_entry(row, explanation, note))
    return entries


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _ask_model(chat_turn: ChatTurn, message: str, cfg: Any, url: str, limits: TurnLimits) -> str:
    # report.run is synchronous (FastAPI runs the route in a worker thread). asyncio.run fails
    # inside a running event loop, so say so plainly; the caller turns it into a note.
    if _loop_running():
        raise RuntimeError("the explainer needs a synchronous caller; an event loop is running")
    turn = chat_turn(message, [], cfg=cfg, mcp_server_url=url, system_prompt=SYSTEM_PROMPT, limits=limits)
    return asyncio.run(turn)


def _default_chat_turn() -> ChatTurn:
    from backend.chat.providers import run_configured_chat_turn

    return run_configured_chat_turn


def _app_config() -> Any:
    from backend.config import config

    return config


def explain_unmatched(
    report: Mapping[str, Any],
    owner: str,
    *,
    chat_turn: Optional[ChatTurn] = None,
    cfg: Any = None,
    mcp_server_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """``[{expected_date, account, status, explanation, note}]`` for each unmatched contribution.

    Empty when nothing is missing, a different amount or late. ``explanation`` is
    None when the model is not configured, fails, or its text fails a check;
    ``note`` then says which. ``cfg`` and ``mcp_server_url`` default to the app
    config; ``chat_turn`` defaults to the configured provider (tests pass a fake).
    """
    rows = unmatched_results(report) if needs_explanation(report) else []
    if not rows:
        return []
    cfg = cfg if cfg is not None else _app_config()
    url = mcp_server_url or getattr(cfg, "mcp_server_url", None)
    if not url:
        return [_entry(row, None, NOTE_NOT_CONFIGURED) for row in rows]
    facts = render_facts(report, rows)
    limits = TurnLimits(
        allowed_tools=READ_ONLY_TOOLS, max_iterations=MAX_TOOL_CALL_ROUNDS, max_tokens=MAX_OUTPUT_TOKENS
    )
    message = build_user_message(report, owner, facts)
    try:
        reply = _ask_model(chat_turn or _default_chat_turn(), message, cfg, url, limits)
    except Exception as exc:  # noqa: BLE001 - the deterministic report stands without explanations
        logger.warning(
            "Allowance guardian explainer failed for %s: %s",
            sanitise_log_value(owner),
            sanitise_log_value(type(exc).__name__),
        )
        return [_entry(row, None, NOTE_FAILED) for row in rows]
    return interpret_reply(rows, reply, facts, limits)
