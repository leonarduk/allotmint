# backend/common/holding_utils.py
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.common.constants import (
    ACQUIRED_DATE, HOLD_DAYS_MIN, COST_BASIS_GBP, EFFECTIVE_COST_BASIS_GBP,
    UNITS, TICKER, _PRICES_JSON
)
from backend.timeseries.cache import load_meta_timeseries_range, get_price_for_date


# ───────────── helpers ─────────────
def _parse_date(val) -> Optional[dt.date]:
    if val is None:
        return None
    if isinstance(val, dt.date):
        return val
    if isinstance(val, dt.datetime):
        return val.date()
    try:
        return dt.datetime.fromisoformat(str(val)).date()
    except Exception:
        return None

def _nearest_weekday(d: dt.date, forward: bool) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1 if forward else -1)
    return d

def load_latest_prices(path: Path = _PRICES_JSON) -> Dict[str, float]:
    try:
        with Path(path).open(encoding="utf-8") as f:
            return {k.upper(): float(v) for k, v in json.load(f).items()}
    except Exception:
        return {}

# ─────── cost basis (single source of truth) ───────
def _derived_cost_basis_close_px(
    ticker: str, exchange: str, acq: dt.date, cache: dict[str, float]
) -> Optional[float]:
    """Find a close price near acquisition date (±2 weekdays). Cached by key."""
    start = _nearest_weekday(acq - dt.timedelta(days=2), False)
    end   = _nearest_weekday(acq + dt.timedelta(days=2), True)
    key   = f"{ticker}.{exchange}_{acq}"
    if key in cache:
        return cache[key]

    df = load_meta_timeseries_range(ticker, exchange, start_date=start, end_date=end)
    if df is None or df.empty:
        return None
    if "close" not in df.columns and "Close" in df.columns:
        df = df.rename(columns={"Close": "close"})
    if "close" not in df.columns or df["close"].empty:
        return None
    px = float(df["close"].iloc[0])
    cache[key] = px
    return px

def get_effective_cost_basis_gbp(
    h: Dict[str, Any],
    price_cache: dict[str, float],
    latest_prices: dict[str, float],
) -> float:
    """
    If booked cost exists, use it. Otherwise derive:
      units * (close near acquisition OR latest cache price).
    """
    units = float(h.get(UNITS, 0) or 0)
    booked = float(h.get(COST_BASIS_GBP) or 0.0)
    if booked > 0:
        return round(booked, 2)

    full = (h.get(TICKER) or "").upper()
    ticker, exchange = (full.split(".", 1) + ["L"])[:2]
    acq = _parse_date(h.get(ACQUIRED_DATE))

    close_px = None
    if acq:
        close_px = _derived_cost_basis_close_px(ticker, exchange, acq, price_cache)
    if close_px is None:
        close_px = latest_prices.get(full)  # last resort

    if close_px is None:
        return 0.0

    return round(units * float(close_px), 2)

# ───────────── canonical enrichment ─────────────
def enrich_holding(
    h: Dict[str, Any],
    today: dt.date,
    price_cache: dict[str, float],
    latest_prices: dict[str, float],
) -> Dict[str, Any]:
    """
    Canonical enrichment used by both owner and group builders.
    Produces the same keys in both paths.
    """
    out = dict(h)  # do not mutate caller
    full = (out.get(TICKER) or "").upper()
    ticker, exchange = (full.split(".", 1) + ["L"])[:2]

    # default acquired date if missing
    if out.get(ACQUIRED_DATE) is None:
        out[ACQUIRED_DATE] = (today - dt.timedelta(days=365)).isoformat()

    acq = _parse_date(out.get(ACQUIRED_DATE))
    if acq:
        days = (today - acq).days
        out["days_held"] = days
        out["sell_eligible"] = days >= HOLD_DAYS_MIN
        out["eligible_on"] = (acq + dt.timedelta(days=HOLD_DAYS_MIN)).isoformat()
        out["days_until_eligible"] = max(0, HOLD_DAYS_MIN - days)
    else:
        out["days_held"] = None
        out["sell_eligible"] = False
        out["eligible_on"] = None
        out["days_until_eligible"] = None

    # Effective cost basis (always computed)
    ecb = get_effective_cost_basis_gbp(out, price_cache, latest_prices)
    out[EFFECTIVE_COST_BASIS_GBP] = ecb

    # Choose cost for gains: prefer booked cost if present, else effective
    cost_for_gain = float(out.get(COST_BASIS_GBP) or 0.0) or ecb

    # Current price as of "yesterday" (your app constraint)
    asof = dt.datetime.combine(today - dt.timedelta(days=1), dt.time.min)
    px = get_price_for_date(exchange, out, ticker, date=asof)
    units = float(out.get(UNITS, 0) or 0)

    out["price"] = px  # legacy name used in parts of UI
    out["current_price_gbp"] = px

    if px is not None:
        mv = round(units * float(px), 2)
        out["market_value_gbp"] = mv
        out["gain_gbp"] = round(mv - cost_for_gain, 2)
        out["unrealized_gain_gbp"] = out["gain_gbp"]
    else:
        out["market_value_gbp"] = None
        out["gain_gbp"] = None
        out["unrealized_gain_gbp"] = None

    # Optional: provenance
    out["cost_basis_source"] = "book" if float(out.get(COST_BASIS_GBP) or 0.0) > 0 else "derived"

    return out
