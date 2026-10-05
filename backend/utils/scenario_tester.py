"""Utility helpers for scenario testing.

Includes helpers for price shocks and applying historical events to
portfolios.
"""

from __future__ import annotations

import datetime as dt
import math
from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

import pandas as pd

from backend.common.constants import (
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
)
from backend.common.prices import get_price_gbp
from backend.common.sector_labels import is_cash_instrument
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


# A close more than this many calendar days after the wanted date is not a
# usable proxy for it (e.g. the instrument only started trading later).
_MAX_PRICE_GAP_DAYS = 7


def _price_on_or_after(df: pd.DataFrame, date_col: str, price_col: str, target: dt.date) -> float | None:
    mask = (df[date_col] >= target) & (df[date_col] <= target + dt.timedelta(days=_MAX_PRICE_GAP_DAYS))
    if not mask.any():
        return None
    try:
        return float(df.loc[mask, price_col].iloc[0])
    except Exception:
        return None


def _forward_returns(
    ticker: str,
    exchange: str,
    event_date: dt.date,
    horizons: Mapping[str, int] = _HORIZONS,
) -> Dict[str, float | None]:
    end = event_date + dt.timedelta(days=max(horizons.values()) + _MAX_PRICE_GAP_DAYS)
    df = load_meta_timeseries_range(ticker, exchange, start_date=event_date, end_date=end)
    if df is None or df.empty:
        return {k: None for k in horizons}

    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)
    df = df.copy().reset_index()

    nm = {c.lower(): c for c in df.columns}
    date_col = nm.get("date") or nm.get("index") or df.columns[0]
    price_col = _close_column(df)
    if not price_col:
        return {k: None for k in horizons}
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    df = df.sort_values(date_col)

    base = _price_on_or_after(df, date_col, price_col, event_date)
    if base is not None and not math.isfinite(base):
        base = None

    results: Dict[str, float | None] = {}
    for label, days in horizons.items():
        tgt = event_date + dt.timedelta(days=days)
        end_price = _price_on_or_after(df, date_col, price_col, tgt)
        if end_price is not None and not math.isfinite(end_price):
            end_price = None
        if base is not None and end_price is not None:
            results[label] = end_price / base - 1.0
        else:
            results[label] = None
    return results


# Below this share of invested value with real price history, a horizon is
# reported as unavailable instead of being extrapolated from the few covered
# holdings.
_MIN_COVERAGE = 0.5


def _holding_returns(
    portfolio: Dict[str, Any],
    event_date: dt.date,
    horizon_days: Mapping[str, int],
    proxy_returns: Mapping[str, float | None],
) -> list[tuple[float, Dict[str, float | None]]]:
    """Return ``(market_value, {label: return | None})`` for each priced holding.

    A holding's own forward return is used where available, then the proxy
    index's; cash is held flat. ``None`` means neither had prices.
    """

    rows: list[tuple[float, Dict[str, float | None]]] = []
    cache: Dict[str, Dict[str, float | None]] = {}
    for acct in portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            mv = float(h.get("market_value_gbp") or 0.0)
            if mv == 0.0:
                continue
            full = (h.get("ticker") or "").upper()
            if is_cash_instrument(full, h.get("instrument_type")):
                rows.append((mv, {k: 0.0 for k in horizon_days}))
                continue
            tkr, ex = _parse_full_ticker(full)
            key = f"{tkr}.{ex}"
            if key not in cache:
                cache[key] = _forward_returns(tkr, ex, event_date, horizon_days)
            own = cache[key]
            rows.append((mv, {k: own.get(k) if own.get(k) is not None else proxy_returns.get(k) for k in horizon_days}))
    return rows


def _shock_horizon(rows: list[tuple[float, Dict[str, float | None]]], label: str) -> tuple[float | None, float]:
    """Return ``(shocked_total, coverage)`` for one horizon.

    Holdings without any return move with the value-weighted return of those
    that have one, provided at least ``_MIN_COVERAGE`` of the value is covered.
    """

    invested = sum(mv for mv, _ in rows)
    covered = [(mv, rets[label]) for mv, rets in rows if rets[label] is not None]
    covered_mv = sum(mv for mv, _ in covered)
    coverage = covered_mv / invested if invested else 0.0
    if coverage < _MIN_COVERAGE:
        return None, coverage
    covered_return = sum(mv * r for mv, r in covered) / covered_mv
    return invested * (1 + covered_return), coverage


def apply_historical_event_portfolio(
    portfolio: Dict[str, Any],
    event: Mapping[str, Any] | None,
    *,
    horizons: Mapping[str, int] | None = None,
) -> Dict[str, Dict[str, float | None]]:
    """Return shocked portfolio valuations for a historical ``event``.

    ``event`` must define ``date`` and ``proxy_index``. ``horizons`` maps a
    result label to a day offset (defaults to ``_HORIZONS``). Each result has
    ``total_value_gbp``, ``delta_gbp`` and ``coverage_pct`` (share of invested
    value with real price history). Totals are ``None`` when coverage is too
    low to say anything, never a fabricated number.
    """

    if not event or not event.get("date"):
        raise ValueError("event with a date must be provided")
    horizon_days = dict(horizons or _HORIZONS)

    baseline = float(portfolio.get("total_value_estimate_gbp") or 0.0)
    if baseline == 0.0:
        baseline = sum(float(a.get("value_estimate_gbp") or 0.0) for a in portfolio.get("accounts", []))

    event_date = _parse_date(event["date"])
    proxy_returns: Dict[str, float | None] = {k: None for k in horizon_days}
    if event.get("proxy_index"):
        proxy_tkr, proxy_ex = _parse_full_ticker(event["proxy_index"])
        proxy_returns = _forward_returns(proxy_tkr, proxy_ex, event_date, horizon_days)

    rows = _holding_returns(portfolio, event_date, horizon_days, proxy_returns)
    result: Dict[str, Dict[str, float | None]] = {}
    for label in horizon_days:
        total, coverage = _shock_horizon(rows, label)
        result[label] = {
            "total_value_gbp": None if total is None else round(total, 2),
            "delta_gbp": None if total is None else round(total - baseline, 2),
            "coverage_pct": round(coverage * 100, 1),
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
    shape ``{ticker: {horizon: return}}``. ``event`` (with ``date`` and
    ``proxy_index``) is required; ``event_id``/``date`` alone are rejected.
    """

    if event is None:
        raise ValueError("event must be provided")

    return apply_historical_event(portfolio, event, horizons=horizons)


def apply_historical_event(
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
