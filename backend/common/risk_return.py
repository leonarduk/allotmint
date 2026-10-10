"""Return vs volatility points for the "Returns vs Volatility" dashboard chart.

Every portfolio point (the whole group, each owner, each owner's account) is
rebuilt from the transaction ledger by :mod:`backend.common.ledger_performance`,
so deposits and withdrawals are not mistaken for gains or losses. Benchmarks
(headline indices such as ``^FTSE`` or any priced ticker) come from their
daily closes. Both use the same estimators: the geometrically chained return
over the window and the annualised standard deviation of daily returns.

Index levels (``^``-prefixed Yahoo symbols) are price returns in the index's
own currency; other tickers are GBP closes from the timeseries cache.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Sequence

import pandas as pd

from backend.common import group_portfolio, instruments, ledger_performance
from backend.common import portfolio as portfolio_mod
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import cache_only
from backend.utils.lazy_import import lazy_import
from backend.utils.pricing_dates import PricingDateCalculator

yf = lazy_import("yfinance")

logger = logging.getLogger(__name__)

# A close on or before the window start must exist even across holidays.
_BENCHMARK_SLACK_DAYS = 7

# Index closes per (symbol, start, end). The end is the reporting date, so an
# entry goes stale only when that date moves on; failed downloads are not
# cached, so a transient Yahoo error is retried on the next request.
_INDEX_CLOSES: Dict[tuple[str, date, date], pd.Series] = {}
_INDEX_CACHE_MAX = 64


@dataclass(frozen=True)
class RiskReturn:
    """Return over a window and the annualised volatility of its daily returns.

    ``sharpe_annual_return`` is the return annualised over trading days that
    ``ledger_performance.sharpe_ratio`` uses, so the chart's Sharpe ratio at a
    given risk-free rate matches the reports'.
    """

    period_return: float | None
    annualised_return: float | None
    volatility: float | None
    sharpe_annual_return: float | None = None

    def as_dict(self) -> Dict[str, float | None]:
        return {
            "period_return": self.period_return,
            "annualised_return": self.annualised_return,
            "volatility": self.volatility,
            "sharpe_annual_return": self.sharpe_annual_return,
        }


def stats_from_returns(returns: pd.Series, after: date, through: date) -> RiskReturn:
    """Chained return, annualised return and volatility for days in ``(after, through]``."""
    total = ledger_performance.chained_return(returns, after, through)
    return RiskReturn(
        period_return=total,
        annualised_return=ledger_performance.annualise(total, (through - after).days),
        volatility=ledger_performance.annualised_volatility(returns, after, through),
        sharpe_annual_return=ledger_performance.trading_day_annual_return(returns, after, through),
    )


class _MemoLoader:
    """``load_gbp_closes`` memoised per instrument across the ledger rebuilds.

    Each account, owner and the group replays a different date range, but the
    same instruments recur; one load from the earliest start serves them all.
    """

    def __init__(self) -> None:
        self._closes: Dict[str, tuple[date, date, pd.Series]] = {}

    def __call__(self, key: str, start: date, end: date) -> pd.Series:
        cached = self._closes.get(key)
        if cached is None or start < cached[0] or end > cached[1]:
            lo = min(start, cached[0]) if cached else start
            hi = max(end, cached[1]) if cached else end
            cached = (lo, hi, ledger_performance.load_gbp_closes(key, lo, hi))
            self._closes[key] = cached
        closes = cached[2]
        if closes.empty:
            # No price history comes back as a bare ``Series(dtype=float)``
            # with a RangeIndex, which can't be compared with a date (#10454).
            return closes
        window = closes[(closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))]
        window.attrs = dict(closes.attrs)
        return window


def _ledger_stats(
    ledgers: Sequence[ledger_performance.AccountLedger],
    holdings: Sequence[Mapping[str, Any]],
    end: date,
    after: date,
    loader: _MemoLoader,
) -> RiskReturn | None:
    perf = ledger_performance.build_ledger_performance(ledgers, end, holdings=holdings, price_loader=loader)
    if perf is None or perf.values.empty:
        return None
    return stats_from_returns(perf.returns, after, end)


def _holdings(pf: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [h for acct in pf.get("accounts", []) for h in acct.get("holdings", []) if isinstance(h, dict)]


def _point(kind: str, owner: str | None, account: str | None, stats: RiskReturn) -> Dict[str, Any]:
    return {"kind": kind, "owner": owner, "account": account, **stats.as_dict()}


def _owner_points(
    owner: str, end: date, after: date, loader: _MemoLoader
) -> tuple[List[Dict[str, Any]], List[ledger_performance.AccountLedger], List[Mapping[str, Any]]]:
    """Points for ``owner`` and each of their accounts, plus the inputs for pooling."""
    ledgers = ledger_performance.load_owner_ledgers(owner)
    if not ledgers:
        return [], [], []
    holdings = _holdings(portfolio_mod.build_owner_portfolio(owner, pricing_date=end))
    points: List[Dict[str, Any]] = []
    owner_stats = _ledger_stats(ledgers, holdings, end, after, loader)
    if owner_stats is not None:
        points.append(_point("owner", owner, None, owner_stats))
    for ledger in ledgers:
        account_stats = _ledger_stats([ledger], holdings, end, after, loader)
        if account_stats is not None:
            points.append(_point("account", owner, ledger.account, account_stats))
    return points, ledgers, holdings


def compute_group_risk_return(slug: str, days: int = 365, *, pricing_date: date | None = None) -> Dict[str, Any]:
    """Return/volatility points for group ``slug``, its members and their accounts.

    Members without a transaction ledger are listed in ``missing_members``
    and left out of every point, including the group's. Prices are read
    cache-only, as for the other ledger-based figures. ``group_members``
    raises ``ValueError`` for an unknown slug.
    """
    members = group_portfolio.group_members(slug)
    end = PricingDateCalculator(reporting_date=pricing_date).reporting_date
    after = end - timedelta(days=days)
    loader = _MemoLoader()
    points: List[Dict[str, Any]] = []
    pooled: List[ledger_performance.AccountLedger] = []
    pooled_holdings: List[Mapping[str, Any]] = []
    missing: List[str] = []
    with cache_only():
        for member in members:
            member_points, ledgers, holdings = _owner_points(member, end, after, loader)
            if not ledgers:
                missing.append(member)
                continue
            points.extend(member_points)
            pooled.extend(ledgers)
            pooled_holdings.extend(holdings)
        group_stats = _ledger_stats(pooled, pooled_holdings, end, after, loader) if pooled else None
    if group_stats is not None:
        points.insert(0, _point("group", None, None, group_stats))
    return {
        "group": slug,
        "days": days,
        "start": after.isoformat(),
        "end": end.isoformat(),
        "points": points,
        "missing_members": missing,
    }


def _index_closes(symbol: str, start: date, end: date) -> pd.Series:
    """Daily closes for a Yahoo index symbol (``^FTSE``...) in its own currency."""
    key = (symbol, start, end)
    cached = _INDEX_CLOSES.get(key)
    if cached is not None:
        return cached
    closes = _download_index_closes(symbol, start, end)
    if not closes.empty:
        if len(_INDEX_CLOSES) >= _INDEX_CACHE_MAX:
            _INDEX_CLOSES.pop(next(iter(_INDEX_CLOSES)))
        _INDEX_CLOSES[key] = closes
    return closes


def _download_index_closes(symbol: str, start: date, end: date) -> pd.Series:
    frame = yf.download(
        symbol,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    if frame is None or frame.empty or "Close" not in frame:
        return pd.Series(dtype=float)
    closes = frame["Close"]
    if isinstance(closes, pd.DataFrame):
        closes = closes.iloc[:, 0]
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    closes.index = pd.DatetimeIndex(pd.to_datetime(closes.index)).tz_localize(None).normalize()
    return closes[~closes.index.duplicated(keep="last")].sort_index()


def benchmark_closes(ticker: str, start: date, end: date) -> pd.Series:
    """Index closes from Yahoo for ``^`` symbols, otherwise cached GBP closes.

    A listed ticker must be a known instrument (``data/instruments``) and is
    read cache-only: a request must not make the server fetch, and write to
    the timeseries and corporate-actions caches for, any ticker it names.
    The ticker passed on is the catalogue's own string rather than the
    request's, which also keeps path-injection analysis from tracing request
    data into those cache paths.
    """
    if ticker.startswith("^"):
        return _index_closes(ticker, start, end)
    known = _catalogue_ticker(ticker)
    if known is None:
        return pd.Series(dtype=float)
    with cache_only():
        return ledger_performance.load_gbp_closes(known, start, end)


def _catalogue_entry(ticker: str) -> Dict[str, Any] | None:
    """The instrument catalogue's metadata for ``ticker``, or ``None`` if unknown."""
    wanted = ticker.upper()
    for instrument in instruments.list_instruments():
        known = str(instrument.get("ticker") or "").upper()
        if known and known == wanted:
            return instrument
    return None


def _catalogue_ticker(ticker: str) -> str | None:
    """The instrument catalogue's spelling of ``ticker``, or ``None`` if unknown."""
    entry = _catalogue_entry(ticker)
    return str(entry["ticker"]).upper() if entry else None


def _benchmark_description(ticker: str) -> Dict[str, str | None]:
    """Display ``name`` and ``sector`` for a listed ticker; both ``None`` for an index."""
    entry = None if ticker.startswith("^") else _catalogue_entry(ticker)
    if not entry:
        return {"name": None, "sector": None}
    return {"name": entry.get("name") or None, "sector": entry.get("sector") or None}


def compute_benchmark_risk_return(
    ticker: str, days: int = 365, *, pricing_date: date | None = None
) -> Dict[str, Any] | None:
    """Return/volatility of ``ticker`` over the same window as the portfolio points.

    ``None`` when no closes are available for the window.
    """
    end = PricingDateCalculator(reporting_date=pricing_date).reporting_date
    after = end - timedelta(days=days)
    try:
        closes = benchmark_closes(ticker, after - timedelta(days=_BENCHMARK_SLACK_DAYS), end)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("No closes for %s: %s", sanitise_log_value(ticker), sanitise_log_value(exc))
        return None
    if closes.empty:
        return None
    # Rebase onto the last close on or before the window start, so the first
    # in-window return is measured from there rather than dropped. A ticker
    # with no close that early (listed mid-window) is measured from its first
    # close instead, like an account opened mid-window.
    base = closes[closes.index <= pd.Timestamp(after)]
    in_window = closes[closes.index > pd.Timestamp(after)]
    series = pd.concat([base.iloc[-1:], in_window]) if not base.empty else in_window
    returns = series.pct_change().dropna()
    if returns.empty:
        return None
    stats = stats_from_returns(returns, after, end)
    return {
        "ticker": ticker,
        "days": days,
        "start": after.isoformat(),
        "end": end.isoformat(),
        **_benchmark_description(ticker),
        **stats.as_dict(),
    }
