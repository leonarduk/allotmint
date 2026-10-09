"""Prompt and no-advice guardrails for the plan-drift brief agent (#10475).

The agent reports facts and arithmetic only. The prompt forbids
recommendations, and :func:`advice_violations` checks the output anyway: a
brief whose prose fails the check is not published with that prose.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from backend.common.investment_plan import InvestmentPlan

SYSTEM_PROMPT = """\
You write a short, factual monthly brief comparing an investor's portfolio with
their own written investment plan. You are not an adviser.

Hard rules:
- Report facts and arithmetic only. Never recommend, suggest or imply buying,
  selling, holding, switching, topping up, trimming or rebalancing anything,
  and never name a product, fund or provider to move to. Do not use "you
  should", "consider", "recommend" or imperative verbs about trading.
- The drift table, cash figures, review dates and changes are given to you as
  FACTS. Quote those numbers exactly; never recompute or round them differently.
- Use tools only to evaluate the plan's review triggers and assumptions. You
  can only read data; you cannot change anything.
- For each trigger give a verdict: "fired", "not_fired" or "cant_evaluate".
  "fired"/"not_fired" must cite evidence: the tool you called, the field you
  read, its value and (where the tool gives one) its source and date. If the
  data to decide is not available, say "cant_evaluate" and why. Never guess.
- Keep the prose under 200 words, plain English, no headings.

Reply with ONE JSON object and nothing else:
{
  "triggers": [
    {"trigger": "<exact trigger text>", "verdict": "fired|not_fired|cant_evaluate",
     "reason": "<one factual sentence>",
     "evidence": [{"tool": "<tool name>", "field": "<field path>", "value": <value>,
                   "source": "<source or null>", "as_of": "<date or null>"}]}
  ],
  "assumptions": [
    {"key": "<assumption key>", "status": "matches|differs|cant_check",
     "current_value": <value or null>, "reason": "<one factual sentence>",
     "evidence": [ ...same shape as above... ]}
  ],
  "prose": "<the brief>"
}
"""


def build_user_message(plan: InvestmentPlan, facts: Mapping[str, Any], today: str) -> str:
    """The plan's free-text parts plus the deterministic facts, as one message."""
    payload = {
        "today": today,
        "owner": plan.owner,
        "plan_summary": plan.summary,
        "review_triggers": list(plan.review.triggers),
        "assumptions": [a.model_dump(mode="json", exclude_none=True) for a in plan.assumptions],
        "facts": {key: value for key, value in facts.items() if key != "holdings_snapshot"},
    }
    return (
        "Evaluate each review trigger and assumption with the tools, then write the brief.\n"
        "FACTS (authoritative, do not recompute):\n" + json.dumps(payload, indent=1, default=str)
    )


# --------------------------------------------------------------------------- guardrails

_TRADE_VERBS = (
    r"buy|sell|hold|switch|move|rebalance|invest|reinvest|top\s+up|trim|reduce|increase|add|"
    r"purchase|dispose|transfer|allocate|deploy|shift|swap|cut"
)
_ADVICE_PATTERNS = [
    # Second-person modal advice: "you should", "you may want to", ...
    re.compile(r"\byou\s+(?:should|must|could|might|may|need\s+to|ought\s+to|want\s+to)\b", re.I),
    re.compile(r"\b(?:we|i)\s+(?:recommend|suggest|advise|would)\b", re.I),
    re.compile(r"\b(?:recommend\w*|advis(?:e|able|ed)|suggest(?:s|ed|ion)?)\b", re.I),
    re.compile(r"\b(?:consider|worth)\s+(?:\w+ing)\b", re.I),
    re.compile(r"\bit\s+(?:would|may|might)\s+be\s+(?:wise|sensible|prudent|worth)\b", re.I),
    # A trade verb followed by an amount: "sell £6,000", "buy 6.2pp".
    re.compile(rf"\b(?:{_TRADE_VERBS})\s+(?:about\s+|around\s+|roughly\s+)?(?:£|\$|€|\d)", re.I),
    # A sentence (or bullet) that opens with a trade verb in the imperative.
    re.compile(rf"(?:^|[.!?:;]\s+|\n)\s*(?:[-*•]\s*)?(?:{_TRADE_VERBS})\b(?!\w)", re.I),
    re.compile(r"\b(?:switch|move)\s+(?:to|into)\b", re.I),
]


def advice_violations(text: str) -> list[str]:
    """Phrases in ``text`` that read as a recommendation to trade (empty = clean)."""
    found: list[str] = []
    for pattern in _ADVICE_PATTERNS:
        found.extend(match.group(0).strip(" .!?:;-*•\n") for match in pattern.finditer(text or ""))
    return found


_PP_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*(?:pp|percentage\s+points?)\b", re.I)


def drift_figure_mismatches(text: str, drift: Mapping[str, Any]) -> list[str]:
    """``pp`` figures in ``text`` that match no drift (or tolerance) figure in the deterministic table."""
    known = {abs(float(row["drift_pp"])) for row in drift.get("rows", []) if row.get("drift_pp") is not None}
    if drift.get("tolerance_pct") is not None:
        known.add(abs(float(drift["tolerance_pct"])))
    return [
        m.group(0)
        for m in _PP_RE.finditer(text or "")
        if not any(abs(abs(float(m.group(1))) - k) < 0.05 for k in known)
    ]
