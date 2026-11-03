"""A short, factual LLM summary of a decision draft's context snapshot (#10487).

The deterministic snapshot (prices, weights, trailing returns, valuation) is raw
JSON; a few plain sentences make it readable at review time months later. The
summary only restates the snapshot: it never gives reasons for the decision
(the owner writes those in ``reason``, which this module never touches) and
never advises.

The model runs through the configured chat provider with
:data:`~backend.decision_journal.capture.READ_ONLY_CONTEXT_TOOLS` as its tool
allowlist, so it is neither offered nor allowed to call anything else (every
write tool included). Any failure -- not configured, provider error, a reply
that fails the facts-only checks -- leaves the draft without a summary and
records why in ``snapshot["summary_note"]``; drafting never blocks on it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Coroutine, Mapping, Optional

from backend.chat.turn_limits import TurnLimits
from backend.decision_journal.capture import READ_ONLY_CONTEXT_TOOLS
from backend.logging_setup import sanitise_log_value
from backend.plan_brief.prompt import advice_violations, known_numbers, percent_figure_mismatches

logger = logging.getLogger(__name__)

#: (message, history, *, cfg, mcp_server_url, system_prompt, limits) -> reply text.
ChatTurn = Callable[..., Coroutine[Any, Any, str]]

MAX_TOOL_CALL_ROUNDS = 3
MAX_OUTPUT_TOKENS = 400
MAX_SUMMARY_CHARS = 1200

NOTE_NOT_CONFIGURED = "No context summary: the summary model is not configured (MCP_SERVER_URL unset)."
NOTE_FAILED = "No context summary: the summary model failed."
NOTE_REJECTED = "No context summary: the model's text failed the facts-only checks."

#: Snapshot keys this module writes; they are not facts to summarise.
_SUMMARY_KEYS = ("summary", "summary_note")

SYSTEM_PROMPT = """\
You summarise the market and portfolio context recorded when an investor made a
decision, so they can read it months later. You are not an adviser.

Hard rules:
- Restate facts from the SNAPSHOT only, in 2-4 plain sentences, under 120 words.
- Quote figures exactly as given; never compute new ones.
- Never give reasons, motives or intentions for the decision, and never say why
  it was made: the investor writes their own reasoning.
- Never recommend, suggest or imply any action, and never judge whether the
  decision was good or bad.
- You may call the read-only tools offered only to check a fact the snapshot
  lacks; you cannot change anything.
- Reply with the summary text only: no headings, no lists, no JSON.
"""

_REASONING_PATTERNS = [
    re.compile(r"\bbecause\b", re.I),
    re.compile(r"\b(?:in order|so as) to\b", re.I),
    re.compile(r"\b(?:reason|reasons|reasoning|rationale|motivation|motive)\b", re.I),
    re.compile(r"\b(?:to|in a bid to)\s+(?:lock in|take profits?|cut losses|de-?risk|reduce risk)\b", re.I),
    re.compile(
        r"\b(?:the )?(?:owner|investor|you|they|he|she)\s+"
        r"(?:wanted|decided|chose|felt|believed|thought|expected|hoped|intended|feared)\b",
        re.I,
    ),
    re.compile(r"\b(?:good|bad|wise|smart|poor|sound|right|wrong)\s+(?:decision|call|move|trade)\b", re.I),
]


def reasoning_violations(text: str) -> list[str]:
    """Phrases in ``text`` that give the decision's reasons or judge it (empty = clean)."""
    return [match.group(0) for pattern in _REASONING_PATTERNS for match in pattern.finditer(text or "")]


def facts_of(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """The snapshot without any summary fields this module added."""
    return {key: value for key, value in snapshot.items() if key not in _SUMMARY_KEYS}


def build_user_message(snapshot: Mapping[str, Any]) -> str:
    return "Summarise this decision context.\nSNAPSHOT (authoritative):\n" + json.dumps(
        facts_of(snapshot), indent=1, sort_keys=True, default=str
    )


def summary_problems(text: str, snapshot: Mapping[str, Any], limits: TurnLimits) -> list[str]:
    """Why ``text`` can't be stored as a facts-only summary (empty when it can)."""
    if not text:
        return ["empty reply"]
    problems = [f"advice wording: {p}" for p in advice_violations(text)]
    problems += [f"reasoning wording: {p}" for p in reasoning_violations(text)]
    known = known_numbers(facts_of(snapshot), [call.get("result") for call in limits.tool_log])
    problems += [f"figure not in the snapshot: {p}" for p in percent_figure_mismatches(text, known)]
    if len(text) > MAX_SUMMARY_CHARS:
        problems.append(f"longer than {MAX_SUMMARY_CHARS} characters")
    return problems


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _default_chat_turn() -> ChatTurn:
    from backend.chat.providers import run_configured_chat_turn

    return run_configured_chat_turn


def _app_config() -> Any:
    from backend.config import config

    return config


def _ask_model(chat_turn: ChatTurn, snapshot: Mapping[str, Any], cfg: Any, url: str, limits: TurnLimits) -> str:
    # Drafts are built in a sync route (FastAPI runs it in a worker thread), so no loop is running.
    if _loop_running():
        raise RuntimeError("the context summary needs a synchronous caller; an event loop is running")
    turn = chat_turn(
        build_user_message(snapshot), [], cfg=cfg, mcp_server_url=url, system_prompt=SYSTEM_PROMPT, limits=limits
    )
    return asyncio.run(turn)


def summarise_context(
    snapshot: Mapping[str, Any],
    *,
    chat_turn: Optional[ChatTurn] = None,
    cfg: Any = None,
    mcp_server_url: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """``(summary, None)``, or ``(None, note)`` saying why there is no summary. Never raises.

    ``cfg`` and ``mcp_server_url`` default to the app config; ``chat_turn``
    defaults to the configured provider (tests pass a fake).
    """
    cfg = cfg if cfg is not None else _app_config()
    url = mcp_server_url or getattr(cfg, "mcp_server_url", None)
    if not url:
        return None, NOTE_NOT_CONFIGURED
    limits = TurnLimits(
        allowed_tools=READ_ONLY_CONTEXT_TOOLS,
        max_iterations=MAX_TOOL_CALL_ROUNDS,
        max_tokens=MAX_OUTPUT_TOKENS,
        raise_at_cap=True,
    )
    try:
        text = (_ask_model(chat_turn or _default_chat_turn(), snapshot, cfg, url, limits) or "").strip()
    except Exception as exc:  # noqa: BLE001 - the draft is still useful without a summary
        logger.warning("Decision journal context summary failed: %s", sanitise_log_value(type(exc).__name__))
        return None, NOTE_FAILED
    problems = summary_problems(text, snapshot, limits)
    if problems:
        logger.warning("Decision journal context summary rejected: %s", sanitise_log_value(problems))
        return None, NOTE_REJECTED
    return text, None


def add_context_summary(draft: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """``draft`` with ``snapshot.summary`` (or ``snapshot.summary_note``); ``reason`` is left as it was."""
    snapshot = facts_of(draft.get("snapshot") or {})
    summary, note = summarise_context(snapshot, **kwargs)
    snapshot.update({"summary": summary} if summary else {"summary_note": note})
    return {**draft, "snapshot": snapshot}
