"""
Instrument-level helpers for AllotMint
=====================================

Public API
----------

• timeseries_for_ticker(ticker, days=365)
• positions_for_ticker(group_slug, ticker)
• instrument_summaries_for_group(group_slug)   ← used by InstrumentTable
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import List, Dict, Any

from backend.common.group_portfolio import build_group_portfolio
from backend.common.portfolio import (
    _nearest_weekday,
    load_latest_prices,
)
from backend.common.prices import load_prices_for_tickers
from backend.timeseries.cache import load_meta_timeseries_range, has_cached_meta_timeseries
from backend.timeseries.fetch_meta_timeseries import run_all_tickers

# ───────────────────────────────────────────────────────────────
# Historical close series
# ───────────────────────────────────────────────────────────────
def timeseries_for_ticker(ticker: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Return last *days* rows of close prices for *ticker* – empty list if none.
    """

    # Only fetch if not cached
    if not has_cached_meta_timeseries(ticker, "L"):
        run_all_tickers([ticker])
    df = load_prices_for_tickers([ticker])

    if df.empty or {"date", "close_gbp"} - set(df.columns):
        return []

    cutoff = dt.date.today() - dt.timedelta(days=days)
    df = df[df["date"] >= cutoff.isoformat()]

    return [
        {"date": r["date"], "close_gbp": float(r["close_gbp"])}
        for _, r in df.iterrows()
    ]

# ───────────────────────────────────────────────────────────────
# Last price + %-changes helper (cached)
# ───────────────────────────────────────────────────────────────
_latest_prices = load_latest_prices()  # JSON cache (GBP)

@lru_cache(maxsize=2048)
def _price_and_changes(ticker: str) -> Dict[str, Any]:
    """
    Return:
        last_price_gbp, last_price_date,
        change_7d_pct,  change_30d_pct
    """
    today = dt.date.today()

    full_ticker = next((k for k in _latest_prices if k.split(".")[0] == ticker), None)
    last_px = _latest_prices.get(full_ticker or ticker.upper())

    if not ticker or ticker.strip() == "" or not full_ticker or last_px is None:
        return {
            "last_price_gbp": None,
            "last_price_date": None,
            "change_7d_pct": None,
            "change_30d_pct": None,
        }

    ticker_only, exchange = (full_ticker.split(".", 1) + ["L"])[:2]

    def _close_n_days_ago(days: int) -> float | None:
        date = _nearest_weekday(today - dt.timedelta(days=days), False)
        try:
            df = load_meta_timeseries_range(ticker_only, exchange, start_date=date, end_date=date)
            if df is None or df.empty:
                return None
            col = "close" if "close" in df.columns else "Close" if "Close" in df.columns else None
            return float(df[col].iloc[0]) if col else None
        except Exception:
            return None

    px_7 = _close_n_days_ago(7)
    px_30 = _close_n_days_ago(30)

    return {
        "last_price_gbp": last_px,
        "last_price_date": today.isoformat(),
        "change_7d_pct": None if px_7 is None else (last_px / px_7 - 1) * 100,
        "change_30d_pct": None if px_30 is None else (last_px / px_30 - 1) * 100,
    }

# ───────────────────────────────────────────────────────────────
# Positions by ticker
# ───────────────────────────────────────────────────────────────
def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    gp = build_group_portfolio(group_slug)
    rows: list[Dict[str, Any]] = []

    for owner in gp["members"]:
        for acct in gp["accounts"]:
            for h in acct.get("holdings", []):
                if h.get("ticker") == ticker and h.get("units", 0):
                    rows.append(
                        {
                            "owner": owner,
                            "units": h["units"],
                            "market_value_gbp": h["market_value_gbp"],
                            "cost_basis_gbp": h.get("effective_cost_basis_gbp", 0),
                            "unrealised_gain_gbp": h.get("gain_gbp", 0),
                        }
                    )
    return rows

# ───────────────────────────────────────────────────────────────
# Instrument table rows
# ───────────────────────────────────────────────────────────────
def instrument_summaries_for_group(group_slug: str) -> List[Dict[str, Any]]:
    """
    Aggregate holdings in *group_slug* into per-ticker summary for InstrumentTable.
    """
    gp = build_group_portfolio(group_slug)
    rows: dict[str, Dict[str, Any]] = {}

    for acct in gp["accounts"]:
        for h in acct.get("holdings", []):
            tkr = h.get("ticker", "").strip()
            name = h.get("name", "").strip()
            if not tkr or not name:
                continue  # skip blank or malformed

            entry = rows.setdefault(
                tkr,
                {
                    "ticker": tkr,
                    "name": name,
                    "units": 0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp": 0.0,
                }
            )
            entry["units"] += h.get("units", 0)
            entry["market_value_gbp"] += h.get("market_value_gbp", 0) or 0
            entry["gain_gbp"] += h.get("gain_gbp", 0) or 0

    for tkr, entry in rows.items():
        if not tkr or tkr.strip() == "":
            continue  # 🛑 Skip empty or invalid tickers
        entry.update(_price_and_changes(tkr))

    return sorted(rows.values(), key=lambda r: r["market_value_gbp"], reverse=True)
