"""Plan class -> long-history block mapping and the plan's real annual return series.

:data:`CLASS_BLOCKS` is the single, documented table. Each plan class
(:data:`backend.common.investment_plan.PLAN_CLASSES`) maps to a weighted mix of
long-history blocks. ``exact`` is False when the blocks only stand in for the
class (e.g. corporate bonds replayed as 10-year gilts); those classes count
towards ``proxy_share_pct``. ``fallback`` names a block used, and reported, in
years where a primary block has no data; with no fallback such years are
unavailable and any window touching them is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from backend.retirement.long_history import LongHistory


@dataclass(frozen=True)
class ClassMapping:
    blocks: Mapping[str, float]
    exact: bool
    note: str
    fallback: Optional[str] = None


CLASS_BLOCKS: dict[str, ClassMapping] = {
    "equity": ClassMapping(
        {"us_equity_gbp": 0.6, "ex_us_dev_equity_gbp": 0.4},
        exact=False,
        note="global equity replayed as 60% US / 40% ex-US developed equity (a fixed mix, not market-cap weights)",
    ),
    "small_cap_value": ClassMapping(
        {"us_small_value_gbp": 1.0},
        exact=False,
        note="US small value (academic, gross of costs, an upper bound for investable funds); "
        "US equity before its data starts",
        fallback="us_equity_gbp",
    ),
    "long_gilts": ClassMapping(
        {"uk_govt_bond_10y": 1.0}, exact=False, note="10-year gilt total return (no separate long-gilt series)"
    ),
    "intermediate_gilts": ClassMapping({"uk_govt_bond_10y": 1.0}, exact=True, note="10-year gilt total return"),
    "short_gilts": ClassMapping({"uk_cash": 1.0}, exact=False, note="UK cash (no separate short-gilt series)"),
    "index_linked": ClassMapping(
        {"uk_govt_bond_10y": 1.0}, exact=False, note="nominal 10-year gilts (no index-linked series)"
    ),
    "overseas_government": ClassMapping(
        {"uk_govt_bond_10y": 1.0}, exact=False, note="UK 10-year gilts (no overseas government bond series)"
    ),
    "corporate_bonds": ClassMapping(
        {"uk_govt_bond_10y": 1.0}, exact=False, note="UK 10-year gilts (no corporate bond series)"
    ),
    "gold": ClassMapping(
        {"gold_gbp": 1.0}, exact=True, note="gold in GBP (dollar price fixed before 1971; data from 1928)"
    ),
    "other_commodities": ClassMapping({"gold_gbp": 1.0}, exact=False, note="gold (no long-run commodity series)"),
    "commodities": ClassMapping({"gold_gbp": 1.0}, exact=False, note="gold (no long-run commodity series)"),
    "cash": ClassMapping({"uk_cash": 1.0}, exact=True, note="UK Treasury bills / Bank Rate"),
}


@dataclass(frozen=True)
class PlanReturns:
    """Real annual returns of the plan mix, rebalanced each year; ``None`` = year unavailable."""

    real_returns: dict[int, Optional[float]]
    blocks_used: dict[str, float]
    proxy_share_pct: float
    proxies: list[dict]
    fallback_years: dict[str, list[int]]
    unavailable_reasons: dict[int, list[str]]


def _normalise(weights_pct: Mapping[str, float]) -> dict[str, float]:
    unknown = sorted(set(weights_pct) - set(CLASS_BLOCKS))
    if unknown:
        raise ValueError(f"No long-history mapping for plan class {unknown[0]!r}")
    total = sum(weights_pct.values())
    if total <= 0:
        raise ValueError("Plan weights must sum to more than zero")
    return {key: value / total for key, value in weights_pct.items() if value > 0}


def _class_return(mapping: ClassMapping, history: LongHistory, year: int) -> tuple[Optional[float], bool, str]:
    """(nominal return, used fallback, missing block name) for one class in ``year``."""
    values = {block: history.value(block, year) for block in mapping.blocks}
    present = {block: value for block, value in values.items() if value is not None}
    missing = [block for block in values if block not in present]
    if not missing:
        return sum(share * present[block] for block, share in mapping.blocks.items()), False, ""
    if mapping.fallback is not None:
        fallback_value = history.value(mapping.fallback, year)
        if fallback_value is not None:
            return fallback_value, True, ""
    return None, False, missing[0]


def blocks_used(weights: Mapping[str, float]) -> dict[str, float]:
    """Each block's share of the mix (fractions summing to 1), from the primary mapping."""
    used: dict[str, float] = {}
    for key, weight in weights.items():
        for block, share in CLASS_BLOCKS[key].blocks.items():
            used[block] = round(used.get(block, 0.0) + weight * share, 10)
    return dict(sorted(used.items()))


def _year_return(
    weights: Mapping[str, float], history: LongHistory, year: int, fallback_years: dict[str, list[int]]
) -> tuple[Optional[float], list[str]]:
    reasons: list[str] = []
    cpi = history.cpi.get(year)
    if cpi is None:
        reasons.append("uk_cpi_inflation")
    nominal = 0.0
    for key, weight in weights.items():
        value, used_fallback, missing = _class_return(CLASS_BLOCKS[key], history, year)
        if value is None:
            reasons.append(missing)
            continue
        if used_fallback:
            fallback_years.setdefault(key, []).append(year)
        nominal += weight * value
    if reasons or cpi is None:
        return None, reasons
    return (1.0 + nominal) / (1.0 + cpi) - 1.0, []


def plan_real_returns(weights_pct: Mapping[str, float], history: LongHistory) -> PlanReturns:
    """Real (CPI-deflated) annual return of the plan mix for every year in ``history``."""
    weights = _normalise(weights_pct)
    fallback_years: dict[str, list[int]] = {}
    unavailable: dict[int, list[str]] = {}
    real: dict[int, Optional[float]] = {}
    for year in history.years:
        value, reasons = _year_return(weights, history, year, fallback_years)
        real[year] = value
        if reasons:
            unavailable[year] = reasons
    proxies: list[dict[str, Any]] = [
        {"class": key, "weight_pct": round(weight * 100, 4), "proxy": CLASS_BLOCKS[key].note}
        for key, weight in weights.items()
        if not CLASS_BLOCKS[key].exact
    ]
    return PlanReturns(
        real_returns=real,
        blocks_used=blocks_used(weights),
        proxy_share_pct=round(sum(float(p["weight_pct"]) for p in proxies), 2),
        proxies=proxies,
        fallback_years=fallback_years,
        unavailable_reasons=unavailable,
    )


def _year_ranges(years: list[int]) -> str:
    ranges: list[str] = []
    start = prev = years[0]
    for year in years[1:] + [None]:  # type: ignore[list-item]
        if year is not None and year == prev + 1:
            prev = year
            continue
        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        if year is not None:
            start = prev = year
    return ", ".join(ranges)


def data_notes(returns: PlanReturns) -> list[str]:
    """Human-readable notes on fallbacks and unavailable years."""
    notes = [
        f"{key} used {CLASS_BLOCKS[key].fallback} for {_year_ranges(years)} (no {key} data then)."
        for key, years in sorted(returns.fallback_years.items())
    ]
    by_block: dict[str, list[int]] = {}
    for year, reasons in sorted(returns.unavailable_reasons.items()):
        for block in reasons:
            by_block.setdefault(block, []).append(year)
    notes.extend(
        f"No {block} data for {_year_ranges(years)}; windows touching those years are excluded."
        for block, years in sorted(by_block.items())
    )
    return notes
