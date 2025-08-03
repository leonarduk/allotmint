"""
Instrument-level helpers for AllotMint
=====================================

Public API
----------

• timeseries_for_ticker(ticker, days=365)
• positions_for_ticker(group_slug, ticker)
• instrument_summaries_for_group(group_slug)   ← NEW (used by InstrumentTable)
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import List, Dict, Any

from backend.common.group_portfolio import build_group_portfolio
from backend.common.portfolio import (
    _nearest_weekday,  # already defined in portfolio.py
    load_latest_prices,
)
from backend.common.prices import load_prices_for_tickers
from backend.timeseries.fetch_meta_timeseries import (
    run_all_tickers,
    fetch_meta_timeseries,
)


# ───────────────────────────────────────────────────────────────
# Historical close series
# ───────────────────────────────────────────────────────────────
def timeseries_for_ticker(ticker: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Return last *days* rows of close prices for *ticker* – empty list if none.
    """
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
    Return dict with:
        last_price_gbp, last_price_date,
        change_7d_pct,  change_30d_pct
    Values may be None if data is unavailable.
    """
    today = dt.date.today()
    last_px = _latest_prices.get(ticker.upper())
    if last_px is None:
        return {k: None for k in
                ("last_price_gbp", "last_price_date",
                 "change_7d_pct", "change_30d_pct")}

    def _close_n_days_ago(days: int) -> float | None:
        date = _nearest_weekday(today - dt.timedelta(days=days), False)
        df = fetch_meta_timeseries(ticker, "L", start_date=date, end_date=date)
        if df is None or df.empty:
            return None
        col = "close" if "close" in df.columns else "Close" if "Close" in df.columns else None
        return float(df[col].iloc[0]) if col else None

    px_7  = _close_n_days_ago(7)
    px_30 = _close_n_days_ago(30)

    return {
        "last_price_gbp":  last_px,
        "last_price_date": today.isoformat(),
        "change_7d_pct": (
            None if px_7  is None else (last_px / px_7  - 1) * 100
        ),
        "change_30d_pct": (
            None if px_30 is None else (last_px / px_30 - 1) * 100
        ),
    }

# ───────────────────────────────────────────────────────────────
# Positions by ticker (unchanged)
# ───────────────────────────────────────────────────────────────
def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    gp = build_group_portfolio(group_slug)
    rows: list[Dict[str, Any]] = []

    for owner in gp["members"]:
        for acct in gp["accounts"]:
            for h in acct.get("holdings", []):
                if h["ticker"] == ticker and h.get("units", 0):
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
# NEW: build instrument table rows for a group
# ───────────────────────────────────────────────────────────────
def instrument_summaries_for_group(group_slug: str) -> List[Dict[str, Any]]:
    """
    Aggregate all holdings in *group_slug* into a per-ticker summary suitable
    for InstrumentTable (front-end).
    """
    gp   = build_group_portfolio(group_slug)
    rows: dict[str, Dict[str, Any]] = {}

    for acct in gp["accounts"]:
        for h in acct.get("holdings", []):
            tkr = h["ticker"]
            entry = rows.setdefault(
                tkr,
                {
                    "ticker": tkr,
                    "name":   h["name"],
                    "units":  0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp": 0.0,
                }
            )
            entry["units"]             += h.get("units", 0)
            entry["market_value_gbp"]  += h.get("market_value_gbp", 0) or 0
            entry["gain_gbp"]          += h.get("gain_gbp", 0) or 0

    # add last-price / %-change info
    for tkr, entry in rows.items():
        entry.update(_price_and_changes(tkr))

    # sort by market value descending
    return sorted(rows.values(), key=lambda r: r["market_value_gbp"], reverse=True)
