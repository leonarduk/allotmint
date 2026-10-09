"""Concentration alerts from look-through exposure (#10482).

Reads :func:`backend.common.look_through.compute_look_through` output and
reports, factually, when a single stock (direct plus through funds), a country
or a sector is at or above the owner's threshold, or has moved materially
since the last bot run. Messages state the exposure and where it comes from;
they never suggest an action.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

from backend.common.look_through import COMMODITIES_COUNTRY, NOT_LOOKED_THROUGH, UNKNOWN_LABEL
from backend.common.sector_labels import CASH_SECTOR_LABEL

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "single_stock_pct": 5.0,
    "country_pct": 60.0,
    "sector_pct": 30.0,
    # A move of at least this many percentage points since the last run is reported.
    "material_change_pct": 1.0,
}

# Buckets that are not a country/sector exposure in their own right.
_NOT_EXPOSURES = {CASH_SECTOR_LABEL, NOT_LOOKED_THROUGH, UNKNOWN_LABEL, COMMODITIES_COUNTRY}


def normalise_thresholds(raw: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    """``DEFAULT_THRESHOLDS`` overlaid by valid (finite, 0-100) values from ``raw``."""
    out = dict(DEFAULT_THRESHOLDS)
    for key, value in (raw or {}).items():
        if key not in out or isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and 0 < number <= 100:
            out[key] = number
    return out


def _stock_rows(result: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    total = float(result.get("total_value_gbp") or 0.0)
    # Tickers of the funds that were looked through: a holding's sources that
    # are in this set are funds; any other source is the share held directly.
    fund_tickers = {f.get("ticker") for f in (result.get("coverage") or {}).get("funds") or []}
    rows: Dict[str, Dict[str, Any]] = {}
    for h in result.get("holdings") or []:
        if h.get("kind") != "security" or total <= 0:
            continue
        direct = float(h.get("direct_value_gbp") or 0.0)
        rows[str(h["key"])] = {
            "label": h.get("name") or h["key"],
            "pct": float(h.get("weight_pct") or 0.0),
            "direct_pct": direct / total * 100.0,
            "via_funds_pct": float(h.get("via_funds_value_gbp") or 0.0) / total * 100.0,
            "fund_count": sum(1 for s in h.get("sources") or [] if s.get("ticker") in fund_tickers),
        }
    return rows


def _bucket_rows(buckets: Optional[List[Mapping[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(b["label"]): {"label": str(b["label"]), "pct": float(b.get("weight_pct") or 0.0)}
        for b in buckets or []
        if b.get("label") not in _NOT_EXPOSURES
    }


def snapshot(result: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    """The percentages a later run compares against (``{kind: {key: pct}}``)."""
    return {
        "stock": {k: round(v["pct"], 4) for k, v in _stock_rows(result).items()},
        "country": {k: round(v["pct"], 4) for k, v in _bucket_rows(result.get("countries")).items()},
        "sector": {k: round(v["pct"], 4) for k, v in _bucket_rows(result.get("sectors")).items()},
    }


def _stock_message(row: Mapping[str, Any]) -> str:
    funds = row["fund_count"]
    via = f"{row['via_funds_pct']:.1f}% via {funds} fund{'s' if funds != 1 else ''}"
    if row["direct_pct"] > 0 and funds:
        detail = f"{row['direct_pct']:.1f}% direct + {via}"
    elif funds:
        detail = via
    else:
        detail = "held directly"
    return f"{row['label']} is {row['pct']:.1f}% of the portfolio: {detail}."


def _message(kind: str, row: Mapping[str, Any], previous: Optional[float]) -> str:
    if kind == "stock":
        text = _stock_message(row)
    else:
        text = f"{kind.capitalize()} exposure to {row['label']} is {row['pct']:.1f}% of the portfolio."
    if previous is not None:
        text += f" It was {previous:.1f}% at the last run."
    return text


def _alerts_for(
    kind: str, rows: Dict[str, Dict[str, Any]], threshold: float, material: float, previous: Mapping[str, float]
) -> List[Dict[str, Any]]:
    alerts = []
    for key in sorted(set(rows) | set(previous)):
        row = rows.get(key) or {"label": key, "pct": 0.0, "direct_pct": 0.0, "via_funds_pct": 0.0, "fund_count": 0}
        before = previous.get(key)
        above = row["pct"] >= threshold
        moved = before is not None and abs(row["pct"] - before) >= material
        # A move only matters for an exposure at or above the threshold now or before.
        if not above and not (moved and before is not None and before >= threshold):
            continue
        alerts.append(
            {
                "kind": kind,
                "key": key,
                "label": row["label"],
                "pct": round(row["pct"], 2),
                "previous_pct": None if before is None else round(before, 2),
                "threshold_pct": threshold,
                "reason": "changed" if moved else "above_threshold",
                "message": _message(kind, row, before if moved else None),
            }
        )
    return alerts


def concentration_alerts(
    result: Mapping[str, Any],
    thresholds: Optional[Mapping[str, Any]] = None,
    previous: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> Dict[str, Any]:
    """Alerts for ``result`` (look-through output) against ``thresholds`` and the ``previous`` snapshot."""
    limits = normalise_thresholds(thresholds)
    prev = previous or {}
    material = limits["material_change_pct"]
    alerts = (
        _alerts_for("stock", _stock_rows(result), limits["single_stock_pct"], material, prev.get("stock") or {})
        + _alerts_for(
            "country", _bucket_rows(result.get("countries")), limits["country_pct"], material, prev.get("country") or {}
        )
        + _alerts_for(
            "sector", _bucket_rows(result.get("sectors")), limits["sector_pct"], material, prev.get("sector") or {}
        )
    )
    alerts.sort(key=lambda a: -a["pct"])
    coverage = result.get("coverage") or {}
    return {
        "thresholds": limits,
        "alerts": alerts,
        "total_value_gbp": result.get("total_value_gbp"),
        "not_looked_through_value_gbp": coverage.get("not_covered_value_gbp"),
        "compared_with_previous_run": previous is not None,
    }
