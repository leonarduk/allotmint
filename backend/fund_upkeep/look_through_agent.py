"""Propose a look-through block from a fund's public issuer factsheet (#10492).

For held funds that Morningstar and justETF cannot resolve
(:func:`.look_through_upkeep.refresh_stale` lists them as ``unresolved``,
``reason: "no source"``), the agent reads the issuer's public factsheet and
proposes a ``look_through`` block: country and sector weights, top holdings,
the document date (``as_of``) and the document URL.

It reuses the OCF agent's machinery in :mod:`.charges_agent`: the same tool
loop, the same read-only tool allowlist (``READ_ONLY_TOOLS``), the same
public-URL-only fetcher and the same rule that the cited source must have
been fetched during this run. The answer is validated by
:func:`.proposals.validate_look_through` (which uses the look-through view's
own ``usable_look_through``) and only ever queued for the owner's approval --
nothing is written to instrument metadata here.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Mapping, Optional

from backend.fund_upkeep import charges_agent, proposals

MAX_STEPS = charges_agent.MAX_STEPS
MAX_TOP_HOLDINGS = 25
SOURCE_LABEL = "issuer factsheet"

SYSTEM_PROMPT = (
    "You find the published portfolio breakdown of one fund from its issuer's public factsheet. "
    "Search by ISIN and prefer the issuer's own website. Never use pages that need a login, and "
    "never use paid data feeds. Fetch the document before quoting it, and only report weights the "
    "document states. When done, reply with JSON only: "
    '{"look_through": {"countries": {"<country>": <percent of fund>, ...}, "sectors": '
    '{"<sector>": <percent of fund>, ...}, "top_holdings": [{"name": "<holding>", "isin": '
    '"<ISIN or null>", "weight_pct": <percent of fund>}, ...]}, "source_url": "<the document URL '
    'you fetched>", "document_date": "YYYY-MM-DD", "confidence": "high"|"medium"|"low"} or, if the '
    'factsheet does not give both country and sector weights, {"not_found": "<reason>"}.'
)


def _percent(value: Any) -> Optional[float]:
    """A weight in (0, 100], else ``None`` (booleans and text are not weights)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0 < value <= 100 else None


def _weight_map(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    weights = {str(label).strip(): _percent(weight) for label, weight in raw.items()}
    return {label: weight for label, weight in weights.items() if label and weight is not None}


def _holdings(raw: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        name = str(item.get("name") or "").strip() if isinstance(item, dict) else ""
        weight = _percent(item.get("weight_pct")) if isinstance(item, dict) else None
        if not name or weight is None:
            continue
        isin = str(item.get("isin") or "").strip().upper() or None
        rows.append({"name": name, "isin": isin, "weight_pct": weight})
    return rows[:MAX_TOP_HOLDINGS]


def clean_block(raw: Any) -> Dict[str, Any]:
    """Only the breakdown fields of the model's block, with non-weights dropped.

    Provenance (``source``, ``source_url``, ``as_of``, ``fetched``) is never
    taken from the model: :func:`.proposals.validate_look_through` sets it from
    the validated source URL and document date.
    """
    block = raw if isinstance(raw, dict) else {}
    cleaned: Dict[str, Any] = {
        "countries": _weight_map(block.get("countries")),
        "sectors": _weight_map(block.get("sectors")),
        "source": SOURCE_LABEL,
    }
    holdings = _holdings(block.get("top_holdings"))
    if holdings:
        cleaned["top_holdings"] = holdings
    return cleaned


def propose_look_through(
    fund: Mapping[str, Any],
    *,
    llm: charges_agent.LlmStep,
    toolbox: charges_agent.ReadOnlyToolbox,
    today: Optional[date] = None,
    max_steps: int = MAX_STEPS,
) -> Dict[str, Any]:
    """``{"status": "proposed", "proposal": ...}`` or ``{"status": "not_found"|"rejected", "reason": ...}``."""
    name = fund.get("name") or fund["ticker"]
    request = (
        f"Find the country weights, sector weights and top holdings of {name} "
        f"(ticker {fund['ticker']}, ISIN {fund.get('isin')}) in its issuer's factsheet."
    )

    def validate(answer: Dict[str, Any]) -> Dict[str, Any]:
        raw = {**answer, "look_through": clean_block(answer.get("look_through"))}
        return proposals.validate_look_through({**raw, "ticker": fund["ticker"], "isin": fund.get("isin")}, today=today)

    return charges_agent.propose(
        llm, toolbox, system_prompt=SYSTEM_PROMPT, request=request, validate=validate, max_steps=max_steps
    )
