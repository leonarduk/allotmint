"""The trend-watch investigation: why did a flagged holding turn? (#10476)

One LLM turn per holding through the configured provider loop
(:func:`backend.chat.providers.run_configured_chat_turn`, so local Ollama works),
restricted to the read-only tools in
:data:`backend.chat.tool_switches.TREND_WATCH_TOOLS` and capped at
``trend_watch.max_tool_calls`` calls. The detector's output goes in as input;
the model is told not to recompute indicators.

The model's answer is checked rather than trusted:

* a verdict outside the allowed set becomes ``inconclusive``;
* ``idiosyncratic_deterioration`` stands only when it cites a tool the model
  actually called successfully this turn; otherwise it is ``inconclusive``;
* ``market_wide_move`` stands only when the holding's move was close to its
  benchmark's, or there was no benchmark to compare with;
* text that reads as a trade instruction or price target is withheld.

Without a model (no MCP server configured, or the call failed) the verdict
falls back to the benchmark comparison alone, and the report says so.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from backend.chat.tool_switches import TREND_WATCH_TOOLS, ToolPolicy
from backend.config import TrendWatchConfig, config
from backend.logging_setup import sanitise_log_value
from backend.trend_watch import prompt
from backend.trend_watch.detect import Detection, market_wide
from backend.trend_watch.settings import load_trend_watch_config

logger = logging.getLogger(__name__)

# How much of each tool result is kept as evidence in the stored report.
MAX_RESULT_CHARS = 600

Runner = Callable[[str, ToolPolicy], Awaitable[str]]


class InvestigationUnavailable(RuntimeError):
    """No model can be called in this deployment (for example, no MCP server URL)."""


async def default_runner(message: str, policy: ToolPolicy) -> str:
    """Run one investigation turn through the configured chat provider."""

    from backend.chat.local_tools import LocalTools
    from backend.chat.providers import run_configured_chat_turn

    if not config.mcp_server_url:
        raise InvestigationUnavailable("no MCP server is configured (mcp_server_url), so no investigation was run")
    return await run_configured_chat_turn(
        message,
        [],
        cfg=config,
        mcp_server_url=config.mcp_server_url,
        local_tools=LocalTools(data_tools=True),
        system_prompt=prompt.SYSTEM_PROMPT,
        tool_policy=policy,
    )


def _parse_reply(reply: str) -> Dict[str, Any]:
    """The JSON object in the model's reply; ``{}`` when there is none."""

    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_calls(policy: ToolPolicy) -> List[Dict[str, Any]]:
    return [
        {
            "tool": call["tool"],
            "arguments": call["arguments"],
            "is_error": call["is_error"],
            # A source may itself recommend a trade; the report keeps the facts, not that.
            "result": prompt.redact_advice(str(call["result"])[:MAX_RESULT_CHARS]),
        }
        for call in policy.calls
    ]


def _clean_evidence(raw: Any, called: set[str], notes: List[str]) -> List[Dict[str, Any]]:
    """Evidence items that cite a tool called successfully and give no trade instruction."""

    evidence: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "")
        # Keep falsy values such as 0: the evidence is the audit trail.
        entry = {
            key: ("" if item.get(key) is None else str(item.get(key)))[:MAX_RESULT_CHARS]
            for key in ("tool", "finding", "value", "return_basis", "source")
        }
        if tool not in called:
            notes.append(f"Dropped evidence citing {tool or 'no tool'}, which was not called successfully.")
            continue
        phrases = prompt.advice_phrases(" ".join(entry.values()))
        if phrases:
            notes.append(f"Dropped evidence from {tool} that read as trade advice.")
            continue
        entry["return_basis"] = prompt.relative_basis(entry)
        if entry["return_basis"] == prompt.BASIS_NOT_STATED:
            notes.append(
                f"Evidence from {tool} gives a relative figure without saying whether it is total or price return."
            )
        evidence.append(entry)
    return evidence


def detector_evidence(detection: Detection) -> List[Dict[str, Any]]:
    """The deterministic readings behind the flag, as evidence entries."""

    values = detection.values
    items = [
        {
            "tool": "trend_watch.detect",
            "finding": "Signals on: "
            + ", ".join(detection.active)
            + "; new since last run: "
            + ", ".join(detection.new),
            "value": json.dumps(
                {key: values.get(key) for key in ("price", "sma50", "sma200", "sma200_change", "macd", "rs")}
            ),
            "source": f"cached daily closes to {detection.as_of}",
        }
    ]
    if values.get("excess_move") is not None:
        items.append(
            {
                "tool": "trend_watch.benchmark_comparison",
                "finding": (
                    f"Over {values.get('move_days')} trading days the holding moved {values.get('own_move'):.1%} "
                    f"({values.get('return_basis')} return) and {values.get('benchmark')} moved "
                    f"{values.get('benchmark_move'):.1%} ({values.get('benchmark_return_basis')} return)."
                ),
                "value": f"excess {values.get('excess_move'):+.1%}",
                "source": "cached daily closes",
            }
        )
    return items


def fallback_verdict(detection: Detection, cfg: TrendWatchConfig) -> str:
    """The verdict from the benchmark comparison alone."""

    return prompt.VERDICT_MARKET if market_wide(detection, cfg) else prompt.VERDICT_INCONCLUSIVE


def _settle_verdict(
    parsed: Mapping[str, Any],
    evidence: List[Dict[str, Any]],
    detection: Detection,
    cfg: TrendWatchConfig,
    notes: List[str],
) -> str:
    verdict = parsed.get("verdict")
    if verdict not in (prompt.VERDICT_IDIOSYNCRATIC, prompt.VERDICT_MARKET, prompt.VERDICT_INCONCLUSIVE):
        notes.append(f"The model gave no usable verdict ({verdict!r}); using the benchmark comparison.")
        return fallback_verdict(detection, cfg)
    if verdict == prompt.VERDICT_IDIOSYNCRATIC and not evidence:
        notes.append("The model reported a stock-specific cause without citing a tool result; marked inconclusive.")
        return prompt.VERDICT_INCONCLUSIVE
    comparison = market_wide(detection, cfg)
    if verdict == prompt.VERDICT_MARKET and comparison is False:
        notes.append("The model reported a market-wide move, but the holding fell well beyond its benchmark.")
        return prompt.VERDICT_INCONCLUSIVE
    if verdict == prompt.VERDICT_MARKET and comparison is None:
        notes.append("Market-wide move as reported by the model; there was no benchmark series to check it against.")
    return verdict


async def investigate(
    item: Mapping[str, Any],
    detection: Detection,
    *,
    cfg: Optional[TrendWatchConfig] = None,
    runner: Optional[Runner] = None,
) -> Dict[str, Any]:
    """Investigate one flagged holding; return its verdict, evidence and the tool calls behind it."""

    cfg = cfg or load_trend_watch_config()
    policy = ToolPolicy(allowed=TREND_WATCH_TOOLS, max_calls=cfg.max_tool_calls)
    notes: List[str] = []
    base_evidence = detector_evidence(detection)
    try:
        reply = await (runner or default_runner)(prompt.investigation_message(item), policy)
    except InvestigationUnavailable as exc:
        return {
            "status": "not_run",
            "verdict": fallback_verdict(detection, cfg),
            "summary": None,
            "evidence": base_evidence,
            "tool_calls": [],
            "notes": [f"Investigation not run: {exc}. The verdict uses the benchmark comparison only."],
        }
    except Exception as exc:  # noqa: BLE001 - one holding's failure is reported, not fatal to the run
        logger.warning(
            "Trend-watch investigation failed for %s: %s",
            sanitise_log_value(item.get("ticker")),
            sanitise_log_value(exc),
        )
        return {
            "status": "failed",
            "verdict": fallback_verdict(detection, cfg),
            "summary": None,
            "evidence": base_evidence,
            "tool_calls": _tool_calls(policy),
            "notes": [
                f"Investigation failed ({type(exc).__name__}: {exc}). The verdict uses the benchmark comparison only."
            ],
        }

    parsed = _parse_reply(reply)
    called = {call["tool"] for call in policy.calls if not call["is_error"]}
    evidence = _clean_evidence(parsed.get("evidence"), called, notes)
    verdict = _settle_verdict(parsed, evidence, detection, cfg, notes)
    summary = str(parsed.get("summary") or "").strip() or None
    if summary and prompt.advice_phrases(summary):
        notes.append("The model's summary was withheld because it read as trade advice.")
        summary = None
    return {
        "status": "ok",
        "verdict": verdict,
        "summary": summary,
        "evidence": base_evidence + evidence,
        "tool_calls": _tool_calls(policy),
        "notes": notes,
    }
