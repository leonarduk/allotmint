"""Narrative step of the retirement readiness monitor.

The narrative only *describes* the deterministic report; it never computes.
The facts given to the model are rendered from the report, and the reply is
rejected (falling back to the plain template) if it quotes a figure that is
not in those facts or uses advice wording. The model may check assumptions
with the read-only tools in :data:`READ_ONLY_TOOLS` only.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Mapping, Optional

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

#: The only tools the narrative model may call; every one only reads.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {"get_market_rates", "get_pension_forecast", "get_investment_plan", "summarise_transactions"}
)

#: (system_prompt, facts) -> narrative text.
NarrativeLLM = Callable[[str, str], str]

SYSTEM_PROMPT = (
    "You write a short, plain-English summary of a retirement readiness report for its owner. "
    "Use only the facts given. Copy every figure exactly as written in the facts and add no other "
    "numbers, dates, percentages or amounts. You may call tools to check whether an assumption looks "
    "out of date; if one does, name the assumption in words without quoting any new figure. "
    "Report facts and history only. Never recommend or suggest a withdrawal rate, retirement date, "
    "allocation, product, or any action. End with the adviser note from the facts, unchanged."
)

_ADVICE_PATTERNS = (
    r"\byou should\b",
    r"\byou (?:can|could) (?:safely )?(?:withdraw|retire|afford|spend)\b",
    r"\b(?:we|i) (?:recommend|suggest|advise)\b",
    r"\brecommend(?:s|ed|ation)?\b",
    r"\bconsider (?:withdrawing|retiring|switching|buying|selling|increasing|reducing|moving)\b",
    r"\bsafe to (?:withdraw|retire|spend)\b",
    r"\b(?:buy|sell|switch to|move into|invest in)\b",
)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def advice_violations(text: str) -> list[str]:
    """Advice-like phrases in ``text`` (empty when the wording is factual)."""
    lowered = text.lower()
    return [match.group(0) for pattern in _ADVICE_PATTERNS for match in re.finditer(pattern, lowered)]


def numbers_in(text: str) -> set[float]:
    return {float(raw.replace(",", "")) for raw in _NUMBER_RE.findall(text) if raw.replace(",", "").strip(".")}


def unsupported_numbers(narrative: str, facts: str) -> list[float]:
    """Figures in ``narrative`` that are not in ``facts`` (a fact rounded to whole units also counts)."""
    allowed = numbers_in(facts)
    allowed |= {float(round(value)) for value in allowed}
    return sorted(value for value in numbers_in(narrative) if value not in allowed)


def _money(value: float) -> str:
    return f"£{value:,.2f}"


def _headline_lines(report: Mapping[str, Any]) -> list[str]:
    results = report["results"]
    simulation = results["simulation"]
    projection = results["projection"]
    lines = [
        f"Run date: {report['run_date']}.",
        f"Projected pension pot at retirement age {report['inputs']['retirement_age']}: "
        f"{_money(projection['projected_pot_nominal_gbp'])}, or {_money(projection['start_pot_real_gbp'])} "
        "in today's money.",
        f"Historical windows replayed: {simulation['windows']['count']} of {simulation['horizon_years']} years each.",
    ]
    lines += [
        f"Highest real income sustained in {level['survival_pct']:g}% of windows: {_money(level['income_gbp'])} a year."
        for level in simulation["sustainable_income"]
    ]
    for name in ("worst", "median", "best"):
        row = simulation.get(name)
        if row:
            lines.append(
                f"The {name} window started in {row['start_year']} and sustained "
                f"{_money(row['sustainable_income_gbp'])} a year."
            )
    floor = simulation.get("floor")
    if floor:
        lines.append(
            f"At {_money(floor['at_income_gbp'])} a year the pot fell below {_money(floor['floor_gbp'])} in "
            f"{floor['windows_below_floor']} of {floor['windows_total']} windows."
        )
    return lines


def _change_lines(report: Mapping[str, Any]) -> list[str]:
    lines = []
    change = report.get("attribution")
    if change:
        parts = change["parts_gbp"]
        lines.append(
            f"Since {change['previous_run_date']} the figure moved from {_money(change['previous_income_gbp'])} "
            f"to {_money(change['current_income_gbp'])}: contributions {_money(parts['contributions'])}, "
            f"markets {_money(parts['markets'])}, assumptions {_money(parts['assumptions'])}, "
            f"data revisions {_money(parts['data_revision'])}."
        )
    lines += [f"Changed since the last run: {c['label']}." for c in report.get("assumption_changes", [])]
    lines += list(report.get("market", {}).get("flags", []))
    return lines


def render_facts(report: Mapping[str, Any]) -> str:
    """The deterministic report as plain sentences; also the template narrative."""
    return "\n".join(_headline_lines(report) + _change_lines(report) + list(report["caveats"]))


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _default_llm() -> Optional[NarrativeLLM]:
    """The configured chat provider with the read-only allowlist, or None when no MCP server is set."""
    from backend.chat.providers import run_configured_chat_turn
    from backend.config import config

    url = config.mcp_server_url
    if not url:
        return None

    def call(system_prompt: str, facts: str) -> str:
        # run() is synchronous (FastAPI runs the route in a worker thread). From inside a running
        # event loop asyncio.run would fail, so say so plainly; write_narrative then uses the template.
        if _loop_running():
            raise RuntimeError("narrative model needs a synchronous caller; an event loop is running")
        return asyncio.run(
            run_configured_chat_turn(
                facts, [], cfg=config, mcp_server_url=url, system_prompt=system_prompt, allowed_tools=READ_ONLY_TOOLS
            )
        )

    return call


def _template(facts: str, note: Optional[str] = None) -> dict:
    return {"text": facts, "source": "template", "note": note}


def write_narrative(report: Mapping[str, Any], llm: Optional[NarrativeLLM] = None) -> dict:
    """``{"text", "source": "llm"|"template", "note"}``; any LLM problem falls back to the template."""
    facts = render_facts(report)
    model = llm or _default_llm()
    if model is None:
        return _template(facts)
    try:
        text = (model(SYSTEM_PROMPT, facts) or "").strip()
    except Exception as exc:  # noqa: BLE001 - any provider failure falls back, and is logged
        logger.warning("Retirement readiness narrative failed: %s", sanitise_log_value(exc))
        return _template(facts, "The narrative model failed; showing the plain summary.")
    extra = unsupported_numbers(text, facts)
    advice = advice_violations(text)
    if not text or extra or advice:
        logger.warning(
            "Retirement readiness narrative rejected (figures %s, advice wording %s)",
            sanitise_log_value(extra),
            sanitise_log_value(advice),
        )
        return _template(facts, "The model's summary was rejected by the figure/no-advice checks.")
    return {"text": text, "source": "llm", "note": None}
