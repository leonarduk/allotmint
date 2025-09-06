"""Utility helpers for simple price-shock scenarios."""

from __future__ import annotations

import datetime as dt
import math
from copy import deepcopy
from typing import Any, Dict

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


# ---------------------------------------------------------------------------
# Historical event application

_HORIZONS: Dict[str, int] = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "1y": 365,
}


def _parse_full_ticker(full: str) -> tuple[str, str]:
    parts = (full or "").upper().split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], "L"


def _close_column(df: pd.DataFrame) -> str | None:
    nm = {c.lower(): c for c in df.columns}
    return nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")


def _price_on_or_after(
    df: pd.DataFrame, date_col: str, price_col: str, target: dt.date
) -> float | None:
    mask = df[date_col] >= target
    if not mask.any():
        return None
    try:
        return float(df.loc[mask, price_col].iloc[0])
    except Exception:
        return None


def _forward_returns(
    ticker: str, exchange: str, event_date: dt.date
) -> Dict[str, float | None]:
    end = event_date + dt.timedelta(days=max(_HORIZONS.values()) + 5)
    df = load_meta_timeseries_range(ticker, exchange, start_date=event_date, end_date=end)
    if df is None or df.empty:
        return {k: None for k in _HORIZONS}

    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)

    nm = {c.lower(): c for c in df.columns}
    date_col = nm.get("date") or df.columns[0]
    price_col = _close_column(df)
    if not price_col:
        return {k: None for k in _HORIZONS}

    df = df.copy()
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


def apply_historical_event(portfolio: Dict[str, Any], event: Any) -> Dict[str, Dict[str, float]]:
    """Apply historical forward returns from ``event`` to ``portfolio``.

    For each holding, forward returns from ``event.date`` are computed for the
    horizons defined in ``_HORIZONS``.  Missing data falls back to the event's
    proxy index.  The function returns the simulated portfolio totals and
    deltas versus the current baseline for each horizon.
    """

    baseline = float(portfolio.get("total_value_estimate_gbp") or 0.0)
    if baseline == 0.0:
        baseline = sum(
            float(a.get("value_estimate_gbp") or 0.0) for a in portfolio.get("accounts", [])
        )

    proxy_tkr, proxy_ex = _parse_full_ticker(getattr(event, "proxy", ""))
    proxy_returns = _forward_returns(proxy_tkr, proxy_ex, event.date)

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
                cache[key] = _forward_returns(tkr, ex, event.date)
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
