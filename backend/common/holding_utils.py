# backend/common/holding_utils.py
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from backend.common.constants import (
    ACQUIRED_DATE, HOLD_DAYS_MIN, COST_BASIS_GBP, EFFECTIVE_COST_BASIS_GBP,
    UNITS, TICKER, _PRICES_JSON
)
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import get_scaling_override, apply_scaling


# ───────────── helpers ─────────────
def _parse_date(val) -> Optional[dt.date]:
    if val is None:
        return None
    if isinstance(val, dt.date) and not isinstance(val, dt.datetime):
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


def _lower_name_map(df: pd.DataFrame) -> Dict[str, str]:
    return {c.lower(): c for c in df.columns}


def load_latest_prices(path: Path = _PRICES_JSON) -> Dict[str, float]:
    try:
        with Path(path).open(encoding="utf-8") as f:
            return {k.upper(): float(v) for k, v in json.load(f).items()}
    except Exception:
        return {}


def _close_column(df: pd.DataFrame) -> Optional[str]:
    """
    Prefer Close, fall back to Adj Close, case-insensitive.
    """
    nm = _lower_name_map(df)
    return nm.get("close") or nm.get("adj close") or nm.get("adj_close")


# ─────── cost basis (single source of truth) ───────
def _derived_cost_basis_close_px(
    ticker: str, exchange: str, acq: dt.date, cache: dict[str, float]
) -> Optional[float]:
    """
    Find a scaled close price near acquisition date (±2 weekdays). Cached by key.
    """
    start = _nearest_weekday(acq - dt.timedelta(days=2), False)
    end = _nearest_weekday(acq + dt.timedelta(days=2), True)
    key = f"{ticker}.{exchange}_{acq}"
    if key in cache:
        return cache[key]

    df = load_meta_timeseries_range(ticker, exchange, start_date=start, end_date=end)
    if df is None or df.empty:
        return None

    # apply scaling override
    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)

    col = _close_column(df)
    if not col or df[col].empty:
        return None

    px = float(df[col].iloc[0])
    cache[key] = px
    return px


def _get_price_for_date_scaled(
    ticker: str,
    exchange: str,
    d: dt.date,
    field: str = "Close",
) -> Optional[float]:
    """
    Load a single-day DF, apply scaling override, return the requested field.
    """
    df = load_meta_timeseries_range(ticker=ticker, exchange=exchange,
                                    start_date=d, end_date=d)
    if df is None or df.empty:
        return None

    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)

    nm = _lower_name_map(df)
    col = nm.get(field.lower()) or _close_column(df)
    if not col or df.empty:
        return None

    try:
        return float(df.iloc[0][col])
    except Exception:
        return None


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
    parts = full.split(".", 1)
    ticker = parts[0]
    exchange = parts[1] if len(parts) > 1 else "L"
    acq = _parse_date(h.get(ACQUIRED_DATE))

    close_px = None
    if acq:
        close_px = _derived_cost_basis_close_px(ticker, exchange, acq, price_cache)
    if close_px is None:
        # last resort (already expected to be in *pounds* if you write it that way)
        close_px = latest_prices.get(full)

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
    parts = full.split(".", 1)
    ticker = parts[0]
    exchange = parts[1] if len(parts) > 1 else "L"

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

    # Current price as of "yesterday" (app constraint)
    asof_date = (today - dt.timedelta(days=1))
    px = _get_price_for_date_scaled(ticker, exchange, asof_date)

    units = float(out.get(UNITS, 0) or 0)

    out["price"] = px  # legacy name used in parts of UI
    out["current_price_gbp"] = px

    if px is not None:
        mv = round(units * float(px), 2)
        out["market_value_gbp"] = mv
        out["gain_gbp"] = round(mv - cost_for_gain, 2)

        # aliases for UI compatibility (UK + US)
        out["unrealised_gain_gbp"] = out["gain_gbp"]
        out["unrealized_gain_gbp"] = out["gain_gbp"]

        # percentage gain
        out["gain_pct"] = ((mv - cost_for_gain) / cost_for_gain * 100.0) if cost_for_gain > 0 else None
    else:
        out["market_value_gbp"] = None
        out["gain_gbp"] = None
        out["unrealised_gain_gbp"] = None   # keep both spellings
        out["unrealized_gain_gbp"] = None
        out["gain_pct"] = None

    # provenance
    out["cost_basis_source"] = "book" if float(out.get(COST_BASIS_GBP) or 0.0) > 0 else "derived"

    return out
