"""LLM step of the plan-drift brief (#10475): triggers, assumptions and prose.

The agent runs through the configured provider loop
(:func:`backend.chat.providers.run_configured_chat_turn`) with a read-only
tool allowlist and per-run caps (:class:`backend.chat.turn_limits.TurnLimits`).
Its reply is then checked here rather than trusted:

* a ``fired``/``not_fired`` verdict must cite evidence from a tool the agent
  actually called in this run, otherwise it becomes ``cant_evaluate``;
* a trigger the reply leaves out is ``cant_evaluate``, never ``not_fired``;
* each verdict carries the logged tool calls it rests on;
* prose with advice language, or ``pp`` figures that aren't in the
  deterministic drift table, is replaced by :func:`fallback_prose`.

Without an LLM (no MCP server configured, or the run fails) the brief still
has its deterministic facts and every trigger is ``cant_evaluate`` with the reason.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable, Mapping, Optional

from backend.chat.providers import OPENAI_COMPAT_DEFAULTS, resolve_chat_provider, run_configured_chat_turn
from backend.chat.tool_switches import is_read_only_tool_name
from backend.chat.turn_limits import TurnLimits
from backend.common.investment_plan import InvestmentPlan
from backend.logging_setup import sanitise_log_value
from backend.plan_brief.prompt import (
    SYSTEM_PROMPT,
    advice_violations,
    build_user_message,
    drift_figure_mismatches,
)

logger = logging.getLogger(__name__)

#: The only tools the brief agent is offered or allowed to call. Read-only by
#: construction; ``tests/backend/plan_brief/test_agent.py`` checks it stays so.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "get_allocation",
        "get_portfolio",
        "summarise_transactions",
        "get_market_rates",
        "get_live_prices",
        "get_investment_plan",
        "get_pension_forecast",
    }
)
if not all(is_read_only_tool_name(name) for name in READ_ONLY_TOOLS):
    raise RuntimeError("Plan brief tool allowlist must contain read-only tools only")

MAX_TOOL_CALL_ROUNDS = 6
MAX_OUTPUT_TOKENS = 2000

VERDICTS = ("fired", "not_fired", "cant_evaluate")
ASSUMPTION_STATUSES = ("matches", "differs", "cant_check")

ChatTurn = Callable[..., Awaitable[str]]


def _fmt_gbp(value: Any) -> str:
    return f"£{float(value):,.0f}"


def fallback_prose(facts: Mapping[str, Any]) -> str:
    """A plain factual summary built only from the deterministic facts."""
    drift = facts["drift"]
    parts = [f"Portfolio value {_fmt_gbp(drift['total_value_gbp'])}."]
    outside = [row for row in drift["rows"] if row["status"] in ("over", "under")]
    if outside:
        described = [
            f"{row['label']} is {abs(row['drift_pp']):.1f}pp {'above' if row['drift_pp'] > 0 else 'below'} "
            f"its target ({_fmt_gbp(abs(row['drift_gbp']))})"
            for row in outside
        ]
        parts.append(f"Outside the {drift['tolerance_pct']:g}pp band: " + "; ".join(described) + ".")
    else:
        parts.append(f"Every class is within the {drift['tolerance_pct']:g}pp band of its target.")
    for row in facts["cash"]:
        if row["days_uninvested"] is not None:
            parts.append(
                f"{row['account']} has {_fmt_gbp(row['cash_gbp'])} in cash, "
                f"received since {row['uninvested_since']} ({row['days_uninvested']} days) with no purchase since."
            )
    review = facts["review"]
    if review["due"]:
        parts.append(f"The plan review was due on {review['next_review']}.")
    if facts["stale_evidence"]:
        parts.append(f"{len(facts['stale_evidence'])} evidence item(s) are more than six months old.")
    return " ".join(parts)


def _extract_json(reply: str) -> Optional[dict]:
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


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return "(removed: wording read as advice)" if advice_violations(text) else text


def _evidence(raw: Any, called: set[str]) -> list[dict[str, Any]]:
    """Evidence items naming a tool that was actually called this run."""
    items = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, Mapping) and item.get("tool") in called:
            items.append({key: item.get(key) for key in ("tool", "field", "value", "source", "as_of")})
    return items


def _calls_for(evidence: list[dict[str, Any]], tool_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools = {item["tool"] for item in evidence}
    return [call for call in tool_log if call["tool"] in tools]


def _verdict(text: str, raw: Optional[Mapping[str, Any]], limits: TurnLimits) -> dict[str, Any]:
    if raw is None:
        return {"trigger": text, "verdict": "cant_evaluate", "reason": "The agent gave no verdict.", "evidence": []}
    called = {call["tool"] for call in limits.tool_log if not call["is_error"]}
    evidence = _evidence(raw.get("evidence"), called)
    verdict = raw.get("verdict") if raw.get("verdict") in VERDICTS else "cant_evaluate"
    reason = _clean_text(raw.get("reason"))
    if verdict != "cant_evaluate" and not evidence:
        verdict, reason = "cant_evaluate", f"No tool evidence for the reported verdict ({reason or 'none given'})."
    return {
        "trigger": text,
        "verdict": verdict,
        "reason": reason,
        "evidence": evidence,
        "tool_calls": _calls_for(evidence, limits.tool_log),
    }


def _assumption(key: str, raw: Optional[Mapping[str, Any]], limits: TurnLimits) -> dict[str, Any]:
    if raw is None:
        return {"key": key, "status": "cant_check", "reason": "The agent gave no check.", "evidence": []}
    called = {call["tool"] for call in limits.tool_log if not call["is_error"]}
    evidence = _evidence(raw.get("evidence"), called)
    status = raw.get("status") if raw.get("status") in ASSUMPTION_STATUSES else "cant_check"
    if status != "cant_check" and not evidence:
        status = "cant_check"
    return {
        "key": key,
        "status": status,
        "current_value": raw.get("current_value") if evidence else None,
        "reason": _clean_text(raw.get("reason")),
        "evidence": evidence,
        "tool_calls": _calls_for(evidence, limits.tool_log),
    }


def _by_key(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    return {str(item.get(key)).strip(): item for item in items or [] if isinstance(item, Mapping) and item.get(key)}


def interpret_reply(plan: InvestmentPlan, facts: Mapping[str, Any], reply: str, limits: TurnLimits) -> dict[str, Any]:
    """Validate the agent's reply into trigger verdicts, assumption checks and safe prose."""
    parsed = _extract_json(reply) or {}
    triggers = _by_key(parsed.get("triggers"), "trigger")
    assumptions = _by_key(parsed.get("assumptions"), "key")
    prose = str(parsed.get("prose") or "").strip()
    advice = advice_violations(prose)
    figures = drift_figure_mismatches(prose, facts["drift"])
    problems = []
    if not prose:
        problems.append("no prose returned")
    if advice:
        problems.append("advice language: " + ", ".join(sorted(set(advice))))
    if figures:
        problems.append("drift figures not in the table: " + ", ".join(figures))
    return {
        "triggers": [_verdict(text, triggers.get(text.strip()), limits) for text in plan.review.triggers],
        "assumptions": [_assumption(a.key, assumptions.get(a.key), limits) for a in plan.assumptions],
        "prose": fallback_prose(facts) if problems else prose,
        "prose_source": "deterministic" if problems else "agent",
        "output_check": {"passed": not problems, "problems": problems},
    }


def _offline(plan: InvestmentPlan, facts: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "triggers": [
            {"trigger": t, "verdict": "cant_evaluate", "reason": reason, "evidence": [], "tool_calls": []}
            for t in plan.review.triggers
        ],
        "assumptions": [
            {"key": a.key, "status": "cant_check", "reason": reason, "evidence": [], "tool_calls": []}
            for a in plan.assumptions
        ],
        "prose": fallback_prose(facts),
        "prose_source": "deterministic",
        "output_check": {"passed": True, "problems": []},
        "agent": {"ran": False, "reason": reason},
    }


async def run_agent(
    plan: InvestmentPlan,
    facts: Mapping[str, Any],
    *,
    today: str,
    cfg: Any,
    mcp_server_url: Optional[str],
    chat_turn: Optional[ChatTurn] = None,
) -> dict[str, Any]:
    """Evaluate triggers/assumptions and write the prose; never raises for an LLM failure."""
    if not mcp_server_url:
        return _offline(plan, facts, "The brief agent is not configured (MCP_SERVER_URL unset).")
    limits = TurnLimits(
        allowed_tools=READ_ONLY_TOOLS, max_iterations=MAX_TOOL_CALL_ROUNDS, max_tokens=MAX_OUTPUT_TOKENS
    )
    try:
        reply = await (chat_turn or run_configured_chat_turn)(
            build_user_message(plan, facts, today),
            [],
            cfg=cfg,
            mcp_server_url=mcp_server_url,
            system_prompt=SYSTEM_PROMPT,
            limits=limits,
        )
    except Exception as exc:  # noqa: BLE001 - the deterministic brief is still worth saving
        logger.warning("Plan brief agent failed for %s: %s", sanitise_log_value(plan.owner), sanitise_log_value(exc))
        offline = _offline(plan, facts, f"The brief agent failed: {type(exc).__name__}.")
        offline["agent"]["tool_calls"] = limits.tool_log
        offline["agent"]["usage"] = limits.usage
        return offline
    result = interpret_reply(plan, facts, reply, limits)
    provider = resolve_chat_provider(cfg)
    result["agent"] = {
        "ran": True,
        "provider": provider,
        "model": (
            cfg.bedrock_model_id if provider == "bedrock" else cfg.chat_model or OPENAI_COMPAT_DEFAULTS[provider][1]
        ),
        "usage": limits.usage,
        "tool_calls": limits.tool_log,
    }
    return result
