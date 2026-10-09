"""The trend-watch investigation prompt and the no-advice output check (#10476).

The agent explains why a holding's chart turned; it does not tell the owner what
to do. The prompt says so, and :func:`advice_phrases` checks the model's text
afterwards: anything that reads as a trade instruction or a price target is
withheld from the report rather than shown.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping

from backend.chat.tool_switches import TREND_WATCH_TOOLS

VERDICT_IDIOSYNCRATIC = "idiosyncratic_deterioration"
VERDICT_MARKET = "market_wide_move"
VERDICT_DATA = "data_problem"
VERDICT_INCONCLUSIVE = "inconclusive"
VERDICTS = (VERDICT_IDIOSYNCRATIC, VERDICT_MARKET, VERDICT_DATA, VERDICT_INCONCLUSIVE)

DISCLAIMER = (
    "A review list, not trade instructions: it describes what changed in a holding's chart and what "
    "was found about why. The decision is yours; AllotMint is not a regulated financial adviser."
)

SYSTEM_PROMPT = (
    "You investigate why a holding's price trend has turned down, for the owner's weekly review list. "
    "The detector's readings are given to you as facts; do not recompute indicators.\n"
    "Work out whether the cause is the market or the stock itself:\n"
    "1. Market or stock: compare the move with its benchmark, sector or peers. If they fell together, "
    "that is a market-wide move.\n"
    "2. Fundamentals: earnings or estimate downgrades, a dividend cut, rising debt, falling margins.\n"
    "3. Investment trusts: whether the discount to NAV widened or the NAV itself fell.\n"
    "4. News: profit warnings, management changes, guidance cuts, regulatory events. Cite each source.\n"
    "Use only the tools you are given, and only as many calls as you need.\n"
    "Report facts and evidence only. Never tell the owner to buy, sell, hold, trim or exit, and never give "
    "a price target or a stop level: the decision is theirs.\n"
    "Reply with one JSON object and nothing else:\n"
    '{"verdict": "idiosyncratic_deterioration" | "market_wide_move" | "inconclusive", '
    '"summary": "two or three factual sentences", '
    '"evidence": [{"tool": "<tool you called>", "finding": "<what it showed>", '
    '"value": "<the figure, with units>", "source": "<url or data source, if any>"}]}\n'
    "Use idiosyncratic_deterioration only when a tool result shows a stock-specific cause, and cite it."
)

# Phrases that turn a description into an instruction. Matched case-insensitively
# on word boundaries; a description ("the shares fell", "a dividend cut") does
# not match, an instruction ("consider selling", "sell now") does.
_TRADE_VERBS = (
    r"(?:sell|selling|buy|buying|exit|exiting|trim|trimming|dump|dumping|offload|reduce|add to|top up|hold on)"
)
_MODALS = r"(?:should|must|ought to|need to|may want to|might want to)"
_ADVICE_PATTERNS = [
    re.compile(rf"\b(?:you|the owner|investors?)\s+{_MODALS}\s+{_TRADE_VERBS}\b", re.I),
    re.compile(r"\b(?:i|we)\s+(?:would\s+)?(?:recommend|suggest|advise)\b", re.I),
    re.compile(rf"\b(?:consider|time to|recommend|suggest)\s+{_TRADE_VERBS}\b", re.I),
    re.compile(
        rf"(?:^|[.!?:;]\s+|\n\s*[-*]?\s*){_TRADE_VERBS}\s+(?:now|the|this|your|it|all|some|half|before|on|at|into)\b",
        re.I,
    ),
    re.compile(r"\b(?:price|share price)\s+target\b|\btarget\s+(?:price|of)\b", re.I),
    re.compile(r"\bstop[- ]loss\b|\bstop\s+(?:at|level)\b", re.I),
    re.compile(r"\b(?:strong\s+)?(?:buy|sell)\s+(?:signal|rating|recommendation)\b", re.I),
]


def redact_advice(text: str) -> str:
    """``text`` with any trade-instruction or price-target phrase replaced by a marker."""

    for pattern in _ADVICE_PATTERNS:
        text = pattern.sub(" [trade language removed] ", text)
    return text


def advice_phrases(text: str) -> List[str]:
    """The trade-instruction or price-target phrases found in ``text`` (empty when clean)."""

    if not text:
        return []
    return [match.group(0).strip() for pattern in _ADVICE_PATTERNS for match in pattern.finditer(text)]


def investigation_message(item: Mapping[str, Any]) -> str:
    """The user message for one holding: the detector output and the owner's context, as JSON."""

    payload: Dict[str, Any] = {
        "ticker": item.get("ticker"),
        "name": item.get("name"),
        "instrument_type": item.get("instrument_type"),
        "detection": item.get("detection"),
        "owner_context": item.get("context"),
        "tools_available": sorted(TREND_WATCH_TOOLS),
    }
    return "Investigate this holding's change of direction.\n" + json.dumps(payload, default=str)
