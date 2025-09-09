"""Utility helpers for scenario testing.

Includes helpers for price shocks and applying historical events to
portfolios.
"""

from __future__ import annotations

import datetime as dt
import math
from copy import deepcopy
from typing import Any, Dict, Iterable

import pandas as pd

from backend.common.constants import (
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
)
from backend.common.prices import get_price_gbp
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import (
    apply_scaling,
    get_scaling_override,
)


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

def _scale_portfolio(portfolio: Dict[str, Any], horizons: Iterable[int] | None = None) -> Dict[int, Dict[str, Any]]:
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


# ---------------------------------------------------------------------------
# Historical event application

_HORIZONS: Dict[str, int] = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "1y": 365,
}


def _parse_full_ticker(full: str | Dict[str, str]) -> tuple[str, str]:
    """Split a ticker/exchange combination into its components.

    ``full`` can either be a mapping containing ``ticker`` and ``exchange``
    keys or a string in the format ``"SYMBOL.EXCH"``.  The return value is a
    2-tuple of ``(ticker, exchange)`` with the exchange defaulting to ``"L"``
    (London) when not provided.
    """

    if isinstance(full, dict):
        ticker = (full.get("ticker") or "").upper()
        exch = (full.get("exchange") or "L").upper()
        return ticker, exch

    parts = (full or "").upper().split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], "L"


def _close_column(df: pd.DataFrame) -> str | None:
    nm = {c.lower(): c for c in df.columns}
    return nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")


def _price_on_or_after(df: pd.DataFrame, date_col: str, price_col: str, target: dt.date) -> float | None:
    mask = df[date_col] >= target
    if not mask.any():
        return None
    try:
        return float(df.loc[mask, price_col].iloc[0])
    except Exception:
        return None


def _forward_returns(ticker: str, exchange: str, event_date: dt.date) -> Dict[str, float | None]:
    end = event_date + dt.timedelta(days=max(_HORIZONS.values()) + 5)
    df = load_meta_timeseries_range(ticker, exchange, start_date=event_date, end_date=end)
    if df is None or df.empty:
        return {k: None for k in _HORIZONS}

    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)
    df = df.copy().reset_index()

    nm = {c.lower(): c for c in df.columns}
    date_col = nm.get("date") or nm.get("index") or df.columns[0]
    price_col = _close_column(df)
    if not price_col:
        return {k: None for k in _HORIZONS}
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    df = df.sort_values(date_col)

    base = _price_on_or_after(df, date_col, price_col, event_date)
    if base is not None and not math.isfinite(base):
        base = None

    results: Dict[str, float | None] = {}
    for label, days in _HORIZONS.items():
        tgt = event_date + dt.timedelta(days=days)
        end_price = _price_on_or_after(df, date_col, price_col, tgt)
        if end_price is not None and not math.isfinite(end_price):
            end_price = None
        if base is not None and end_price is not None:
            results[label] = end_price / base - 1.0
        else:
            results[label] = None
    return results


def apply_historical_event_portfolio(
    portfolio: Dict[str, Any],
    event: Any | None = None,
    *,
    event_id: str | None = None,
    date: str | None = None,
    horizons: Iterable[int] | None = None,
) -> Dict[Any, Any]:
    """Return shocked portfolio valuations for a historical event.

    This helper aggregates holding-level returns into portfolio totals for a
    number of preset horizons. It is primarily used by API endpoints that need
    to display the portfolio value and change after an event.  When ``event`` is
    omitted but an ``event_id`` or ``date`` is supplied a simple scaling
    placeholder is returned instead.
    """

    if event is None and (event_id or date):
        return _scale_portfolio(portfolio, horizons)

    if event is None:
        raise ValueError("event must be provided")

    baseline = float(portfolio.get("total_value_estimate_gbp") or 0.0)
    if baseline == 0.0:
        baseline = sum(
            float(a.get("value_estimate_gbp") or 0.0)
            for a in portfolio.get("accounts", [])
        )

    proxy_val = getattr(event, "proxy", None)
    if proxy_val is None and isinstance(event, dict):
        proxy_val = event.get("proxy_index")
    proxy_tkr, proxy_ex = _parse_full_ticker(proxy_val or "")

    event_date = getattr(event, "date", None)
    if event_date is None and isinstance(event, dict):
        event_date = event.get("date")
    proxy_returns = _forward_returns(proxy_tkr, proxy_ex, event_date)

    totals = {k: 0.0 for k in _HORIZONS}
    cache: Dict[str, Dict[str, float | None]] = {}
    for acct in portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            mv = float(h.get("market_value_gbp") or 0.0)
            if mv == 0.0:
                continue
            full = (h.get("ticker") or "").upper()
            tkr, ex = _parse_full_ticker(full)
            key = f"{tkr}.{ex}"
            if key not in cache:
                cache[key] = _forward_returns(tkr, ex, event_date)
            rets = cache[key]
            for label in _HORIZONS:
                r = rets.get(label)
                if r is None:
                    r = proxy_returns.get(label)
                if r is None:
                    r = 0.0
                totals[label] += mv * (1 + r)

    result: Dict[str, Dict[str, float]] = {}
    for label in _HORIZONS:
        total = round(totals[label], 2)
        result[label] = {
            "total_value_gbp": total,
            "delta_gbp": round(total - baseline, 2),
        }
    return result


def _parse_date(val: Any) -> dt.date:
    """Best-effort conversion of ``val`` to ``date``."""
    if isinstance(val, dt.date):
        return val
    try:
        return dt.datetime.fromisoformat(str(val)).date()
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


def _calc_return(ticker: str, exchange: str | None, start: dt.date, horizon: int) -> float | None:
    """Calculate percentage return for ``ticker.exchange`` over ``horizon`` days."""
    end = start + dt.timedelta(days=horizon)
    df = load_meta_timeseries_range(ticker, exchange or "", start_date=start, end_date=end)
    if df.empty or len(df) < 2:
        return None

    scale = get_scaling_override(ticker, exchange or "", None)
    df = apply_scaling(df, scale)

    # Ensure the data covers (most of) the requested horizon.
    last = df.index[-1]
    if isinstance(last, pd.Timestamp):
        last = last.date()
    expected_end = start + dt.timedelta(days=horizon)
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


def apply_historical_returns(
    portfolio: Dict[str, Any],
    event: Dict[str, Any] | None = None,
    *,
    event_id: str | None = None,
    date: str | None = None,
    horizons: Iterable[int] | None = None,
) -> Dict[Any, Any]:
    """Apply a historical event to ``portfolio``.

    Returns per-holding forward returns for the requested ``horizons`` in the
    shape ``{ticker: {horizon: return}}``. If ``event`` is omitted but an
    ``event_id`` or ``date`` is supplied a simple placeholder scaling is
    applied instead.
    """

    if event is None and (event_id or date):
        return _scale_portfolio(portfolio, horizons)

    if event is None:
        raise ValueError("event must be provided")

    return _apply_historical_returns(portfolio, event, horizons=horizons)


def _apply_historical_returns(
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

    # ``proxy_index`` may be provided either as a dict with ``ticker`` and
    # ``exchange`` keys or as a single string like ``"SPY.N"``.  The previous
    # implementation assumed a mapping which caused an ``AttributeError`` when a
    # string was supplied.  By funnelling the value through
    # ``_parse_full_ticker`` we transparently support both forms and keep the
    # rest of the code agnostic to the input type.
    proxy_val = event.get("proxy_index")
    proxy_ticker, proxy_exchange = (None, None)
    if proxy_val:
        proxy_ticker, proxy_exchange = _parse_full_ticker(proxy_val)

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
