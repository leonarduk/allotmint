"""Utility helpers for scenario testing.

Includes helpers for price shocks and applying historical events to
portfolios.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable

import pandas as pd

from backend.common.constants import (
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
)
from backend.common.prices import get_price_gbp
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import apply_scaling, get_scaling_override


def apply_price_shock(portfolio: Dict[str, Any], ticker: str, pct_change: float) -> Dict[str, Any]:
    """Return a new portfolio with ``ticker`` shocked by ``pct_change`` percent.

    ``pct_change`` is interpreted as a percentage (e.g. ``5`` for +5%).
    The function recalculates affected holding metrics, account totals and the
    overall portfolio total.  The original ``portfolio`` is not modified.
    """

    shocked = deepcopy(portfolio)
    target = ticker.upper()
    factor = 1 + pct_change / 100.0

    for acct in shocked.get("accounts", []):
        total = 0.0
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            units = float(h.get("units") or 0.0)
            if tkr == target:
                price = float(h.get("current_price_gbp") or h.get("price") or 0.0)
                if price == 0:
                    cached = get_price_gbp(tkr)
                    price = float(cached or 0.0)
                new_price = price * factor
                cost = float(h.get(EFFECTIVE_COST_BASIS_GBP) or h.get(COST_BASIS_GBP) or 0.0)
                mv = units * new_price
                gain = mv - cost
                h["price"] = h["current_price_gbp"] = round(new_price, 4)
                h["market_value_gbp"] = round(mv, 2)
                h["gain_gbp"] = round(gain, 2)
                h["unrealised_gain_gbp"] = h["unrealized_gain_gbp"] = round(gain, 2)
                h["gain_pct"] = round((gain / cost * 100.0), 2) if cost else None
                h["day_change_gbp"] = round((new_price - price) * units, 2)
            total += float(h.get("market_value_gbp") or 0.0)
        acct["value_estimate_gbp"] = round(total, 2)

    shocked["total_value_estimate_gbp"] = round(
        sum(a.get("value_estimate_gbp") or 0.0 for a in shocked.get("accounts", [])),
        2,
    )
    return shocked

def _scale_portfolio(
    portfolio: Dict[str, Any], horizons: Iterable[int] | None = None
) -> Dict[int, Dict[str, Any]]:
    """Scale ``portfolio`` by a simple factor for each horizon."""

    horizons = list(horizons or [1])
    shocked: Dict[int, Dict[str, Any]] = {}
    for horizon in horizons:
        factor = max(0.0, 1 - horizon / 100.0)
        pf_copy = deepcopy(portfolio)
        for acct in pf_copy.get("accounts", []):
            val = float(acct.get("value_estimate_gbp") or 0.0) * factor
            acct["value_estimate_gbp"] = round(val, 2)
        pf_copy["total_value_estimate_gbp"] = round(
            sum(a.get("value_estimate_gbp") or 0.0 for a in pf_copy.get("accounts", [])),
            2,
        )
        shocked[horizon] = pf_copy
    return shocked

def _parse_date(val: Any) -> date:
    """Best-effort conversion of ``val`` to ``date``."""
    if isinstance(val, date):
        return val
    try:
        return datetime.fromisoformat(str(val)).date()
    except Exception:
        raise ValueError(f"Invalid date value: {val!r}")


def _split_ticker(ticker: str) -> tuple[str, str | None]:
    """Split ``"TICKER.EXCH"`` into symbol and exchange."""
    if "." in ticker:
        sym, exch = ticker.rsplit(".", 1)
        return sym, exch.upper()
    return ticker, None


def _get_close(row: pd.Series) -> float | None:
    for col in ("Close_gbp", "Close", "close_gbp", "close"):
        if col in row and pd.notna(row[col]):
            try:
                return float(row[col])
            except Exception:
                return None
    return None


def _calc_return(ticker: str, exchange: str | None, start: date, horizon: int) -> float | None:
    """Calculate percentage return for ``ticker.exchange`` over ``horizon`` days."""
    end = start + timedelta(days=horizon)
    df = load_meta_timeseries_range(ticker, exchange or "", start_date=start, end_date=end)
    if df.empty or len(df) < 2:
        return None

    scale = get_scaling_override(ticker, exchange or "", None)
    df = apply_scaling(df, scale)

    # Ensure the data covers (most of) the requested horizon.
    last = df.index[-1]
    if isinstance(last, pd.Timestamp):
        last = last.date()
    expected_end = start + timedelta(days=horizon)
    # Allow a few calendar days of tolerance for weekends/holidays.
    if (expected_end - last).days > 3:
        return None

    start_price = _get_close(df.iloc[0])
    end_price = _get_close(df.iloc[-1])
    if not start_price or not end_price:
        return None
    try:
        return (end_price - start_price) / start_price
    except ZeroDivisionError:
        return None


def apply_historical_event(
    portfolio: Dict[str, Any],
    event: Dict[str, Any] | None = None,
    *,
    event_id: str | None = None,
    date: str | None = None,
    horizons: Iterable[int] | None = None,
) -> Dict[Any, Any]:
    """Apply a historical event to ``portfolio``.

    When ``event`` is provided, per-holding returns are calculated for the
    requested ``horizons`` (or those defined within ``event``) and returned as
    ``{ticker: {horizon: return}}``.  If ``event`` is omitted but an
    ``event_id`` or ``date`` is supplied, a simple placeholder scaling is
    applied instead.
    """

    if event is None and (event_id or date):
        return _scale_portfolio(portfolio, horizons)

    if event is None:
        raise ValueError("event must be provided")

    return apply_historical_returns(portfolio, event, horizons=horizons)


def apply_historical_returns(
    portfolio: Dict[str, Any],
    event: Dict[str, Any],
    horizons: Iterable[int] | None = None,
) -> Dict[str, Dict[int, float | None]]:
    """Return holding returns for a historical event.

    ``event`` must define ``date`` and ``proxy_index`` (with ``ticker`` and
    ``exchange``). ``horizons`` is an iterable of day offsets. When omitted, the
    function looks for ``horizons`` inside ``event``.

    For each holding, timeseries data is loaded for each horizon. If no data is
    available the return for that horizon falls back to the event's proxy index.
    """

    start = _parse_date(event.get("date"))
    horizons = list(horizons or event.get("horizons") or [5])
    proxy = event.get("proxy_index") or {}
    proxy_ticker = proxy.get("ticker")
    proxy_exchange = proxy.get("exchange")

    results: Dict[str, Dict[int, float | None]] = {}

    for acct in portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = h.get("ticker") or ""
            sym, exch = _split_ticker(tkr)
            ret_map: Dict[int, float | None] = {}
            for hz in horizons:
                ret = _calc_return(sym, exch, start, hz)
                if ret is None and proxy_ticker:
                    ret = _calc_return(proxy_ticker, proxy_exchange, start, hz)
                ret_map[hz] = ret
            results[tkr] = ret_map

    return results
