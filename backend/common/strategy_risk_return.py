"""Return vs volatility of a strategy for the "Returns vs Volatility" chart.

A strategy is a set of asset-class weights, not tickers, so each class
("sleeve") is priced on the stand-in series the strategy stress test uses
(:data:`backend.common.strategy_stress.STAND_INS`): the first stand-in with a
GBP close on or before the window start (within a week, for holidays) and a
close within a week of its end is used, so every sleeve covers the whole
window rather than being carried flat past a stale cache. Closes have dividends
reinvested where they are stored; a physical gold stand-in pays none, so its
price return is its total return.

The strategy is rebalanced to its target weights every day: its daily return
is the weighted sum of the sleeves' daily returns. A sleeve's return on a
date its market was shut (e.g. a US stand-in on a UK bank holiday) is 0, and
its move is counted on its next close. Cash earns the configured risk-free
rate, accrued by calendar day, rather than being held flat: it is what the
chart's Sharpe line starts from.

As in the stress test, a strategy is never scored on part of its weights:
when any sleeve has no stand-in covering the window, the figures are
``None`` and the sleeves are listed in ``missing``. Prices are read
cache-only, as for the portfolio points.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping, Optional

import pandas as pd

from backend.common import ledger_performance
from backend.common.risk_return import RiskReturn, stats_from_returns
from backend.common.strategies import Strategy
from backend.common.strategy_stress import HELD_FLAT, NO_INCOME_STAND_INS, STAND_INS
from backend.timeseries.cache import cache_only
from backend.timeseries.total_return import PRICE_RETURN_BASIS, TOTAL_RETURN_BASIS
from backend.utils.pricing_dates import PricingDateCalculator

#: A stand-in must have a close this close to (on or before) the window start,
#: and its last close this close to the window end.
START_SLACK_DAYS = 7
END_SLACK_DAYS = 7

_EMPTY_STATS = RiskReturn(None, None, None, None)


def _stand_in_closes(sleeve: str, after: date, end: date) -> Optional[tuple[str, pd.Series, str]]:
    """``(ticker, closes, basis)`` of the first stand-in covering ``after`` to ``end``; ``None`` if none does."""
    start = after - timedelta(days=START_SLACK_DAYS)
    for ticker in STAND_INS.get(sleeve, ()):
        closes, basis = ledger_performance.load_gbp_total_return_closes(ticker, start, end)
        if (
            closes.empty
            or closes.index[0] > pd.Timestamp(after)
            or closes.index[-1] < pd.Timestamp(end - timedelta(days=END_SLACK_DAYS))
        ):
            continue
        return ticker, closes, TOTAL_RETURN_BASIS if ticker in NO_INCOME_STAND_INS else basis
    return None


def _cash_returns(index: pd.DatetimeIndex, rate: float) -> pd.Series:
    """Daily cash returns at an annual ``rate``, accrued over the calendar days between dates."""
    gaps = pd.Series(index, index=index).diff().dt.days.fillna(0)
    return (1.0 + rate) ** (gaps / 365.0) - 1.0


def strategy_daily_returns(
    targets: Mapping[str, float], closes: Mapping[str, pd.Series], cash_rate: float
) -> pd.Series:
    """Daily returns of ``targets`` rebalanced daily, from each priced sleeve's ``closes``.

    ``closes`` covers every target outside :data:`HELD_FLAT`; weights are
    normalised, so targets need not sum to exactly 100. Empty when no sleeve
    is priced: the closes give no trading days to accrue cash over.
    """
    if not closes:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(dict(closes)).sort_index().ffill()
    sleeve_returns = frame.pct_change(fill_method=None).iloc[1:].fillna(0.0)
    cash = _cash_returns(pd.DatetimeIndex(frame.index), cash_rate).iloc[1:]
    total = sum(targets.values())
    daily = pd.Series(0.0, index=sleeve_returns.index)
    for sleeve, weight in targets.items():
        daily = daily + (weight / total) * (cash if sleeve in HELD_FLAT else sleeve_returns[sleeve])
    return daily


def compute_strategy_risk_return(
    strategy: Strategy, days: int = 365, *, cash_rate: float = 0.0, pricing_date: date | None = None
) -> dict[str, Any]:
    """Return/volatility of ``strategy`` over the same window as the portfolio points."""
    end = PricingDateCalculator(reporting_date=pricing_date).reporting_date
    after = end - timedelta(days=days)
    series: dict[str, str] = {}
    closes: dict[str, pd.Series] = {}
    bases: set[str] = set()
    missing: list[str] = []
    with cache_only():
        for sleeve in strategy.targets:
            if sleeve in HELD_FLAT:
                continue
            found = _stand_in_closes(sleeve, after, end)
            if found is None:
                missing.append(sleeve)
                continue
            ticker, sleeve_closes, basis = found
            series[sleeve], closes[sleeve] = ticker, sleeve_closes
            bases.add(basis)
    stats = _EMPTY_STATS
    if not missing:
        # Nothing priced means all cash: accrue it over business days instead.
        returns = (
            strategy_daily_returns(strategy.targets, closes, cash_rate)
            if closes
            else _cash_returns(pd.bdate_range(after, end), cash_rate).iloc[1:]
        )
        if not returns.empty:
            stats = stats_from_returns(returns, after, end)
    return {
        "id": strategy.id,
        "name": strategy.name,
        "builtin": strategy.builtin,
        "targets": dict(strategy.targets),
        "days": days,
        "start": after.isoformat(),
        "end": end.isoformat(),
        "series": series,
        "missing": sorted(missing),
        "return_basis": (
            None if missing else (PRICE_RETURN_BASIS if PRICE_RETURN_BASIS in bases else TOTAL_RETURN_BASIS)
        ),
        "cash_rate": cash_rate,
        **stats.as_dict(),
    }
