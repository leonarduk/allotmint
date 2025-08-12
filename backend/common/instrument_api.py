# backend/common/instrument_api.py
"""
Instrument-level helpers for AllotMint
=====================================

Public API
----------

- timeseries_for_ticker(ticker, days=365)
- positions_for_ticker(group_slug, ticker)
- instrument_summaries_for_group(group_slug)   - used by InstrumentTable
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import List, Dict, Any, Optional

from backend.common.constants import OWNER, ACCOUNTS, HOLDINGS
from backend.common.group_portfolio import build_group_portfolio
from backend.common.holding_utils import load_latest_prices
from backend.common.exchange import guess_exchange
from backend.common.portfolio_utils import list_all_unique_tickers
from backend.timeseries.cache import (
    load_meta_timeseries_range,
    has_cached_meta_timeseries,
)
from backend.timeseries.fetch_meta_timeseries import run_all_tickers


# ───────────────────────────────────────────────────────────────
# Local helpers
# ───────────────────────────────────────────────────────────────
def _nearest_weekday(d: dt.date, forward: bool) -> dt.date:
    """Move to the nearest weekday in the chosen direction (no weekends)."""
    while d.weekday() >= 5:
        d += dt.timedelta(days=1 if forward else -1)
    return d


def _resolve_full_ticker(ticker: str, latest: Dict[str, float]) -> Optional[str]:
    """
    Prefer exact key in latest prices (e.g., 'XDEV.L'); otherwise match by base symbol.
    """
    t = (ticker or "").upper()
    if t in latest:
        return t
    base = t.split(".", 1)[0]
    for k in latest.keys():
        if k.split(".", 1)[0] == base:
            return k
    return None


# Load once; callers can restart process to refresh or we can add a reload later.
_LATEST_PRICES: Dict[str, float] = load_latest_prices(list_all_unique_tickers())


# ───────────────────────────────────────────────────────────────
# Historical close series (GBP where native is GBP, e.g., LSE)
# ───────────────────────────────────────────────────────────────
def timeseries_for_ticker(ticker: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Return last *days* rows of close prices for *ticker* - empty list if none.
    Uses meta timeseries (Yahoo -> Stooq -> FT) and only up to yesterday.
    """
    if not ticker:
        return []

    full = _resolve_full_ticker(ticker, _LATEST_PRICES) or ticker.upper()
    if "." in full:
        sym, ex = full.split(".", 1)
    else:
        sym, ex = full, guess_exchange(full)

    # Only fetch if not cached
    if not has_cached_meta_timeseries(sym, ex):
        try:
            # Best-effort priming; safe to ignore failures since we fall back anyway.
            run_all_tickers([full])
        except Exception:
            pass

    today = dt.date.today()
    end_date = today - dt.timedelta(days=1)
    start_date = end_date - dt.timedelta(days=max(1, days))

    df = load_meta_timeseries_range(sym, ex, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return []

    # Normalize column names
    if "Date" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"Date": "date"})
    if "Close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"Close": "close"})
    if "Close_gbp" in df.columns and "close_gbp" not in df.columns:
        df = df.rename(columns={"Close_gbp": "close_gbp"})
    if "close" not in df.columns and "close_gbp" in df.columns:
        df["close"] = df["close_gbp"]

    if {"date", "close"} - set(df.columns):
        return []

    # Keep rows within cutoff and make sure date is ISO string
    cutoff = end_date - dt.timedelta(days=days - 1)
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        rd = r["date"]
        if isinstance(rd, (dt.datetime, dt.date)):
            rd = rd.date().isoformat() if isinstance(rd, dt.datetime) else rd.isoformat()
        if rd >= cutoff.isoformat():
            close_val = float(r["close"])
            close_gbp_val = float(r.get("close_gbp", close_val))
            out.append({"date": rd, "close": close_val, "close_gbp": close_gbp_val})
    return out


# ───────────────────────────────────────────────────────────────
# Last price + %-changes helper (cached)
# ───────────────────────────────────────────────────────────────
@lru_cache(maxsize=2048)
def _price_and_changes(ticker: str) -> Dict[str, Any]:
    """
    Return:
        last_price_gbp, last_price_date,
        change_7d_pct,  change_30d_pct
    All as-of yesterday per app-wide rule.
    """
    today = dt.date.today()
    yday = today - dt.timedelta(days=1)

    full = _resolve_full_ticker(ticker, _LATEST_PRICES)
    last_px = _LATEST_PRICES.get(full) if full else None

    if not full or last_px is None:
        return {
            "last_price_gbp": None,
            "last_price_date": None,
            "change_7d_pct": None,
            "change_30d_pct": None,
        }

    if "." in full:
        sym, ex = full.split(".", 1)
    else:
        sym, ex = full, guess_exchange(full)

    def _close_on(d: dt.date) -> Optional[float]:
        # Snap to nearest weekday (backwards) and request that exact day.
        snap = _nearest_weekday(d, forward=False)
        df = load_meta_timeseries_range(sym, ex, start_date=snap, end_date=snap)
        if df is None or df.empty:
            return None
        col = "close" if "close" in df.columns else ("Close" if "Close" in df.columns else None)
        return float(df[col].iloc[0]) if col else None

    px_7 = _close_on(yday - dt.timedelta(days=7))
    px_30 = _close_on(yday - dt.timedelta(days=30))

    return {
        "last_price_gbp": float(last_px),
        "last_price_date": yday.isoformat(),
        "change_7d_pct": None if px_7 is None else (float(last_px) / px_7 - 1.0) * 100.0,
        "change_30d_pct": None if px_30 is None else (float(last_px) / px_30 - 1.0) * 100.0,
    }


# ───────────────────────────────────────────────────────────────
# Positions by ticker
# ───────────────────────────────────────────────────────────────
def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    """
    Return enriched positions for the given ticker across a group.
    Uses the already-enriched holdings from group_portfolio (owner added onto each acct).
    """
    gp = build_group_portfolio(group_slug)
    rows: List[Dict[str, Any]] = []

    def _matches(q: str, held: str) -> bool:
        qU, hU = (q or "").upper(), (held or "").upper()
        return hU == qU or hU.split(".", 1)[0] == qU.split(".", 1)[0]

    for acct in gp.get(ACCOUNTS, []):
        owner = acct.get(OWNER)
        acct_type = acct.get("account_type")
        currency = acct.get("currency")
        for h in acct.get(HOLDINGS, []):
            if _matches(ticker, h.get("ticker")) and (h.get("units") or 0):
                rows.append(
                    {
                        "owner": owner,
                        "account_type": acct_type,
                        "currency": currency,
                        "units": h.get("units", 0.0),
                        "current_price_gbp": h.get("current_price_gbp") or h.get("price"),
                        "market_value_gbp": h.get("market_value_gbp"),
                        "book_cost_basis_gbp": h.get("cost_basis_gbp", 0.0),
                        "effective_cost_basis_gbp": h.get("effective_cost_basis_gbp", 0.0),
                        "gain_gbp": h.get("gain_gbp", 0.0),
                        "gain_pct": h.get("gain_pct"),
                        "days_held": h.get("days_held"),
                        "sell_eligible": h.get("sell_eligible"),
                        "days_until_eligible": h.get("days_until_eligible"),
                        "eligible_on": h.get("eligible_on"),
                    }
                )
    return rows


# ───────────────────────────────────────────────────────────────
# Instrument table rows
# ───────────────────────────────────────────────────────────────
def instrument_summaries_for_group(group_slug: str) -> List[Dict[str, Any]]:
    """
    Aggregate holdings in *group_slug* into per-ticker summary for InstrumentTable.
    Adds last price + 7d/30d % changes (as-of yesterday) via the same pipeline.
    """
    gp = build_group_portfolio(group_slug)
    by_ticker: Dict[str, Dict[str, Any]] = {}

    for acct in gp.get(ACCOUNTS, []):
        for h in acct.get(HOLDINGS, []):
            tkr = (h.get("ticker") or "").strip()
            name = (h.get("name") or "").strip()
            if not tkr or not name:
                continue

            entry = by_ticker.setdefault(
                tkr,
                {
                    "ticker": tkr,
                    "name": name,
                    "units": 0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp": 0.0,
                },
            )
            entry["units"] += float(h.get("units") or 0.0)
            entry["market_value_gbp"] += float(h.get("market_value_gbp") or 0.0)
            entry["gain_gbp"] += float(h.get("gain_gbp") or 0.0)

    # Decorate with last price + changes
    for tkr, entry in by_ticker.items():
        if not tkr:
            continue
        entry.update(_price_and_changes(tkr))
        cost = entry["market_value_gbp"] - entry["gain_gbp"]
        entry["gain_pct"] = (entry["gain_gbp"] / cost * 100.0) if cost else None

    return sorted(by_ticker.values(), key=lambda r: r["market_value_gbp"], reverse=True)
