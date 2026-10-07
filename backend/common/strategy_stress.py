"""Replay a historical event against every strategy (#9824).

A strategy is a set of asset-class weights, not tickers, so each class
("sleeve") is replayed on a stand-in series: :data:`STAND_INS` lists listed
instruments per sleeve, oldest-reaching last, and the first with stored prices
for a horizon is used. Returns are total return where dividends are stored
(see :func:`backend.utils.scenario_tester.instrument_forward_returns`) and in
GBP. Cash is held flat, as the holdings scenario holds cash.

Every return is measured from the pre-event close (the last close strictly
before the event date), so the event day's own move counts: Black Monday's 1d
is the 19 Oct 1987 crash. Horizons are calendar days from the event date. The
stand-ins, the pro hook and the portfolio row all follow this rule (#9950).

A strategy's return for a horizon is the weighted sum of its sleeves' returns
with weights fixed at the event date (buy and hold, no rebalancing). It is
``None`` whenever any sleeve has no return, and the missing sleeves are named:
a strategy is never scored on part of its weights, and a sleeve is never
priced on an unrelated proxy such as the event's equity index.

Stand-in coverage in the free build starts in 2008-2012 for most bond
sleeves (gilt ETFs). When allotmint-pro provides
``allotmint_pro.strategy_stress.sleeve_forward_returns`` it fills the
horizons the stand-ins cannot (e.g. synthetic gilts before 2012); its contract
is ``(sleeve, event_date, horizons) -> (returns, return_basis, series_label)``
or ``None``, with returns based on the pre-event close as above.

The owner's current portfolio is replayed through the same holdings engine as
``/scenario/historical`` so it can sit beside the strategies as a baseline. A
holding with no prices of its own on the event date moves with its asset
class's sleeve (from its ``sub_asset_class``, else ``asset_class``), the same
series the strategies use, before the event's proxy index (``SPY``, which
starts in 1993) is tried.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from backend.common.core_optional import missing_package
from backend.common.portfolio import build_owner_portfolio
from backend.common.strategies import Strategy, list_strategies
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import cache_only
from backend.timeseries.total_return import PRICE_RETURN_BASIS, TOTAL_RETURN_BASIS
from backend.utils.scenario_tester import (
    HoldingFallback,
    apply_historical_event_portfolio,
    instrument_forward_returns,
)

logger = logging.getLogger(__name__)

#: Sleeves allotmint-pro's hook knows by its backtest block name instead.
#: Outbound only: the hook's result is keyed by horizon label, never by sleeve name.
PRO_SLEEVE_NAMES: dict[str, str] = {"other_commodities": "commodities"}

ProSleeveReturns = Callable[[str, dt.date, Mapping[str, int]], Optional[tuple[dict[str, Optional[float]], str, str]]]

try:
    from allotmint_pro.strategy_stress import sleeve_forward_returns as _pro_sleeve_returns
except ModuleNotFoundError as exc:
    if not missing_package(exc):
        raise
    _pro_sleeve_returns = None

PRO_SLEEVE_RETURNS: Optional[ProSleeveReturns] = _pro_sleeve_returns

#: Sleeve -> stand-in tickers, preferred first. ``IOO.N`` (iShares Global 100,
#: developed mega-caps only) reaches back to 2000 for equity before ``IWRD.L``
#: (2009) and ``VWRL.L`` (2012). ``BUT.L`` (Brunner) is deliberately absent:
#: before 1988 its stored closes are month-end prices carried across every
#: day, so it reports a fake 0% over a day or a week and would stop
#: allotmint-pro's daily proxies from being asked. ``property`` has no stored
#: stand-in but is listed so its holdings and strategies ask allotmint-pro (US
#: real estate, then UK property companies). Sleeves absent here
#: (``multi_asset``, ``overseas_government``) have no stand-in at all.
STAND_INS: dict[str, tuple[str, ...]] = {
    "equity": ("VWRL.L", "IWRD.L", "IOO.N"),
    "broad_equity": ("VWRL.L", "IWRD.L", "IOO.N"),
    "small_cap_value": ("IJS.N",),
    "bond": ("IGLT.L",),
    "long_gilts": ("GLTL.L",),
    "intermediate_gilts": ("IGLT.L",),
    "short_gilts": ("IGLS.L",),
    "index_linked": ("INXG.L",),
    "corporate_bonds": ("SLXX.L",),
    "commodity": ("DBC.N",),
    "gold": ("PHAU.L",),
    "other_commodities": ("DBC.N",),
    "property": (),
}

#: Stand-ins that pay no income, so their price return is their total return
#: although no dividends are stored (physical gold).
NO_INCOME_STAND_INS = frozenset({"PHAU.L"})

#: Sleeves held at a 0% return over any horizon.
HELD_FLAT = frozenset({"cash"})
CASH_SERIES = "cash (held flat)"

DISCLAIMER = (
    "Historical arithmetic on stored prices; not advice and not a forecast. Each asset class is "
    "replayed on the stand-in series named, with weights fixed at the event date (no rebalancing)."
)


@dataclass(frozen=True)
class SleeveHorizon:
    """One sleeve's return over one horizon and the series it came from (``None`` when unknown)."""

    value: Optional[float] = None
    series: Optional[str] = None
    basis: Optional[str] = None


SleeveReturns = dict[str, SleeveHorizon]
_TickerCache = dict[str, tuple[dict[str, Optional[float]], str]]


def _ticker_returns(
    ticker: str, event_date: dt.date, horizons: Mapping[str, int], cache: _TickerCache
) -> tuple[dict[str, Optional[float]], str]:
    if ticker not in cache:
        returns, basis = instrument_forward_returns(ticker, event_date, horizons)
        cache[ticker] = (returns, TOTAL_RETURN_BASIS if ticker in NO_INCOME_STAND_INS else basis)
    return cache[ticker]


def _fill_from_pro(sleeve: str, event_date: dt.date, horizons: Mapping[str, int], out: SleeveReturns) -> None:
    """Fill the horizons the stand-ins left empty from allotmint-pro, when installed."""
    if PRO_SLEEVE_RETURNS is None or all(h.value is not None for h in out.values()):
        return
    try:
        found = PRO_SLEEVE_RETURNS(PRO_SLEEVE_NAMES.get(sleeve, sleeve), event_date, horizons)
    except Exception as exc:  # a pro bug must not fail the whole stress test; the stand-ins still answer
        logger.warning(
            "allotmint-pro sleeve returns failed for %s on %s: %s",
            sanitise_log_value(sleeve),
            sanitise_log_value(event_date),
            sanitise_log_value(exc),
        )
        return
    if found is None:
        return
    returns, basis, series = found
    for label, current in out.items():
        value = returns.get(label)
        if current.value is None and value is not None:
            out[label] = SleeveHorizon(value, series, basis)


def sleeve_returns(
    sleeve: str, event_date: dt.date, horizons: Mapping[str, int], cache: Optional[_TickerCache] = None
) -> SleeveReturns:
    """Per-horizon return of ``sleeve`` from its first stand-in with prices for that horizon."""
    if sleeve in HELD_FLAT:
        return {label: SleeveHorizon(0.0, CASH_SERIES, TOTAL_RETURN_BASIS) for label in horizons}
    cache = {} if cache is None else cache
    out: SleeveReturns = {label: SleeveHorizon() for label in horizons}
    for ticker in STAND_INS.get(sleeve, ()):
        returns, basis = _ticker_returns(ticker, event_date, horizons, cache)
        for label, current in out.items():
            value = returns.get(label)
            if current.value is None and value is not None:
                out[label] = SleeveHorizon(value, ticker, basis)
    _fill_from_pro(sleeve, event_date, horizons, out)
    return out


def _strategy_horizon(targets: Mapping[str, float], sleeves: Mapping[str, SleeveReturns], label: str) -> dict:
    parts = {sleeve: sleeves[sleeve][label] for sleeve in targets}
    missing = sorted(sleeve for sleeve, part in parts.items() if part.value is None)
    covered = sum(weight for sleeve, weight in targets.items() if sleeve not in missing)
    if missing:
        return {"return_pct": None, "coverage_pct": round(covered, 2), "return_basis": None, "missing": missing}
    total = sum(weight * (parts[sleeve].value or 0.0) for sleeve, weight in targets.items())
    price_only = any(part.basis == PRICE_RETURN_BASIS for part in parts.values())
    return {
        "return_pct": round(total, 2),
        "coverage_pct": round(covered, 2),
        "return_basis": PRICE_RETURN_BASIS if price_only else TOTAL_RETURN_BASIS,
        "missing": [],
    }


def _series_used(targets: Mapping[str, float], sleeves: Mapping[str, SleeveReturns]) -> dict[str, list[str]]:
    """Sleeve -> the distinct series its horizons used, in first-use order."""
    return {
        sleeve: list(dict.fromkeys(h.series for h in sleeves[sleeve].values() if h.series is not None))
        for sleeve in targets
    }


def strategy_result(strategy: Strategy, sleeves: Mapping[str, SleeveReturns], horizons: Mapping[str, int]) -> dict:
    """One strategy's stress row: per-horizon return, coverage and the series used."""
    return {
        "id": strategy.id,
        "name": strategy.name,
        "builtin": strategy.builtin,
        "targets": dict(strategy.targets),
        "horizons": {label: _strategy_horizon(strategy.targets, sleeves, label) for label in horizons},
        "series": _series_used(strategy.targets, sleeves),
    }


def _holding_sleeve(holding: Mapping[str, Any]) -> Optional[str]:
    """The sleeve a holding moves with when it has no prices of its own, or ``None``."""
    for key in (holding.get("sub_asset_class"), holding.get("asset_class")):
        sleeve = str(key or "").strip().lower()
        if sleeve in STAND_INS or sleeve in HELD_FLAT:
            return sleeve
    return None


def _sleeve_as_ticker_returns(
    sleeve: str, returns: SleeveReturns
) -> tuple[str, tuple[dict[str, Optional[float]], str]]:
    """A sleeve's returns in the holdings engine's ``(name, (returns, basis))`` shape."""
    price_only = any(h.basis == PRICE_RETURN_BASIS for h in returns.values() if h.value is not None)
    basis = PRICE_RETURN_BASIS if price_only else TOTAL_RETURN_BASIS
    return f"{sleeve} stand-in", ({label: h.value for label, h in returns.items()}, basis)


def _holding_fallback(event_date: dt.date, horizons: Mapping[str, int], cache: _TickerCache) -> HoldingFallback:
    """Fallback for the holdings engine: a holding's sleeve returns, each sleeve computed once."""
    sleeves: dict[str, SleeveReturns] = {}

    def fallback(holding: Mapping[str, Any]):
        sleeve = _holding_sleeve(holding)
        if sleeve is None:
            return None
        if sleeve not in sleeves:
            sleeves[sleeve] = sleeve_returns(sleeve, event_date, horizons, cache)
        return _sleeve_as_ticker_returns(sleeve, sleeves[sleeve])

    return fallback


def _portfolio_horizon(baseline: float, shocked: Mapping[str, Any]) -> dict:
    delta = shocked.get("delta_gbp")
    return {
        "return_pct": None if delta is None or not baseline else round(delta / baseline * 100.0, 2),
        "coverage_pct": shocked.get("coverage_pct"),
        "return_basis": shocked.get("return_basis"),
        "missing": [],
    }


def portfolio_result(
    owner: str,
    event: Mapping[str, Any],
    horizons: Mapping[str, int],
    accounts_root: Optional[Path],
    cache: Optional[_TickerCache] = None,
) -> Optional[dict]:
    """The owner's current holdings through ``event``, as ``/scenario/historical`` computes them.

    A holding without its own prices moves with its sleeve's stand-in, then the
    event's proxy index. ``None`` when the owner has no account data.
    """
    try:
        portfolio = build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError:
        return None
    baseline = portfolio.get("total_value_estimate_gbp")
    if baseline is None:
        baseline = sum(a.get("value_estimate_gbp") or 0.0 for a in portfolio.get("accounts", []))
        portfolio["total_value_estimate_gbp"] = baseline
    event_date = dt.date.fromisoformat(str(event["date"])[:10])
    fallback = _holding_fallback(event_date, horizons, {} if cache is None else cache)
    shocked = apply_historical_event_portfolio(portfolio, event, horizons=horizons, holding_fallback=fallback)
    return {
        "baseline_total_value_gbp": baseline,
        "horizons": {label: _portfolio_horizon(float(baseline or 0.0), shocked[label]) for label in horizons},
    }


def _event_summary(event: Mapping[str, Any]) -> dict:
    return {"id": event.get("id"), "name": event.get("name"), "date": str(event["date"])}


def stress_strategies(
    owner: str, event: Mapping[str, Any], horizons: Mapping[str, int], accounts_root: Optional[Path] = None
) -> dict:
    """Every strategy of ``owner`` (built-ins first) and their current portfolio through ``event``.

    ``event`` has a ``date`` (ISO string or date) and, for the portfolio's
    unpriced holdings, a ``proxy_index``. Stored prices only: nothing is fetched.
    """
    event_date = dt.date.fromisoformat(str(event["date"])[:10])
    strategies = list_strategies(owner, accounts_root)
    needed = dict.fromkeys(sleeve for strategy in strategies for sleeve in strategy.targets)
    cache: _TickerCache = {}
    with cache_only():
        sleeves = {sleeve: sleeve_returns(sleeve, event_date, horizons, cache) for sleeve in needed}
        portfolio = portfolio_result(owner, event, horizons, accounts_root, cache)
    return {
        "event": _event_summary(event),
        "horizons": list(horizons),
        "portfolio": portfolio,
        "strategies": [strategy_result(s, sleeves, horizons) for s in strategies],
        "pro_history": PRO_SLEEVE_RETURNS is not None,
        "disclaimer": DISCLAIMER,
    }
