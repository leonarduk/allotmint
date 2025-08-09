# backend/common/holding_utils.py
from __future__ import annotations

import datetime as dt
from datetime import date, timedelta
import logging
from typing import Any, Dict, Optional

import pandas as pd

from backend.common.constants import (
    ACQUIRED_DATE, HOLD_DAYS_MIN, COST_BASIS_GBP, EFFECTIVE_COST_BASIS_GBP,
    UNITS, TICKER
)
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import get_scaling_override, apply_scaling

logger = logging.getLogger(__name__)


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


def load_latest_prices(full_tickers: list[str]) -> dict[str, float]:
    """
    Returns mapping like {'HFEL.L': 3.21, 'IEFV.L': 5.77} in GBP.
    - Uses end_date = yesterday
    - Accepts 'HFEL.L' or 'HFEL' (defaults exchange 'L')
    - Skips empties instead of returning 0.00
    """
    result: dict[str, float] = {}
    if not full_tickers:
        return result

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=365)

    for full in full_tickers:
        # --- parse "TICKER[.EXCHANGE]" ---
        if "." in full:
            ticker, exchange = full.split(".", 1)
        else:
            ticker, exchange = full, "L"

        try:
            df = load_meta_timeseries_range(
                ticker=ticker,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                # no data -> don't write a zero; just continue
                continue

            # coerce expected columns and sort by date
            # Accept either 'Close' or 'close' and optionally 'close_gbp'
            cols = {c.lower(): c for c in df.columns}
            close_col = (
                "close_gbp" if "close_gbp" in cols
                else cols.get("close", None)
                or cols.get("close_gbp", None)
            )
            if not close_col:
                # last resort: try 'Close'
                close_col = "Close" if "Close" in df.columns else None
            if not close_col:
                continue

            df = df.sort_values(df.columns[0])  # first col is Date in your feeds
            last = df.iloc[-1]

            val = float(last[close_col])
            if not (val == val and val != float("inf") and val != float("-inf")):
                continue  # skip NaN/inf

            # store using the EXACT key your frontend expects
            key = f"{ticker}.{exchange}"
            result[key] = val

        except Exception as e:
            # keep logging, but don't poison the map with zeros
            logger.warning("latest price fetch failed for %s: %s", full, e)

    logger.info("Latest prices fetched: %d/%d", len(result), len(full_tickers))
    return result


# In-memory map populated elsewhere; exported for consumers that rely on it.
latest_prices: Dict[str, float] = {}


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
    if ticker.upper() in {"CASH", "GBP.CASH", "CASH.GBP"}:
        return 1.0

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
        close_px = price_cache.get(full)

    if close_px is None:
        return 0.0

    return round(units * float(close_px), 2)


# ───────────── canonical enrichment ─────────────
def enrich_holding(
    h: Dict[str, Any],
    today: dt.date,
    price_cache: dict[str, float],
) -> Dict[str, Any]:
    """
    Canonical enrichment used by both owner and group builders.
    Produces the same keys in both paths.
    """
    out = dict(h)  # do not mutate caller
    full = (out.get(TICKER) or "").upper()

    account_ccy = (h.get("currency") or "GBP").upper()
    from backend.common.portfolio_utils import get_security_meta  # local import to avoid circular
    meta = get_security_meta(full)
    out["currency"] = (meta or {}).get("currency")

    if _is_cash(full, account_ccy):
        out = dict(h)
        units = float(out.get(UNITS, 0) or 0.0)
        out["name"] = out.get("name") or _cash_name(full, account_ccy)
        out["currency"] = account_ccy

        # price is 1.0 in account currency
        out["price"] = 1.0
        out["current_price_gbp"] = 1.0 if account_ccy == "GBP" else None  # keep simple; add FX later

        # book cost = value = units; gain = 0
        out["market_value_gbp"] = units if account_ccy == "GBP" else None
        out["gain_gbp"] = 0.0
        out["unrealised_gain_gbp"] = 0.0
        out["unrealized_gain_gbp"] = 0.0
        out["gain_pct"] = 0.0
        out["day_change_gbp"] = 0.0

        # cost basis fields
        out.setdefault(COST_BASIS_GBP, units if account_ccy == "GBP" else None)
        out[EFFECTIVE_COST_BASIS_GBP] = out[COST_BASIS_GBP]

        # eligibility not meaningful for cash
        out["days_held"] = None
        out["sell_eligible"] = True
        out["eligible_on"] = None
        out["days_until_eligible"] = 0
        out["cost_basis_source"] = "cash"

        return out

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
    ecb = get_effective_cost_basis_gbp(out, price_cache)
    out[EFFECTIVE_COST_BASIS_GBP] = ecb

    # Choose cost for gains: prefer booked cost if present, else effective
    cost_for_gain = float(out.get(EFFECTIVE_COST_BASIS_GBP) or 0.0) or ecb

    # Current price as of "yesterday" (app constraint)
    asof_date = (today - dt.timedelta(days=1))
    px = _get_price_for_date_scaled(ticker, exchange, asof_date)

    units = float(out.get(UNITS, 0) or 0)

    out["price"] = px  # legacy name used in parts of UI
    out["current_price_gbp"] = px

    # price one day before to calculate day-on-day change
    prev_date = _nearest_weekday(asof_date - dt.timedelta(days=1), forward=False)
    prev_px = _get_price_for_date_scaled(ticker, exchange, prev_date)

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

    if px is not None and prev_px is not None:
        change_val = (px - prev_px) * units
        out["day_change_gbp"] = round(change_val, 2)
    else:
        out["day_change_gbp"] = None

    # provenance
    out["cost_basis_source"] = "book" if float(out.get(COST_BASIS_GBP) or 0.0) > 0 else "derived"

    return out

# top-level helper
def _is_cash(full: str, account_ccy: str = "GBP") -> bool:
    f = (full or "").upper()
    # allow several spellings
    return f in {f"CASH.{account_ccy}", f"{account_ccy}.CASH", "CASH"}

def _cash_name(full: str, account_ccy: str = "GBP") -> str:
    return f"Cash ({account_ccy})"
