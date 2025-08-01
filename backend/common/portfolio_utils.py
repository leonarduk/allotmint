# backend/common/portfolio_utils.py
"""
Helpers for aggregating holdings across portfolios.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Dict, List, Any

from backend.common.prices import (
    get_latest_closing_prices,
    load_prices_for_tickers,
)
from backend.timeseries.fetch_meta_timeseries import run_all_tickers


# ──────────────────────────────────────────────────────────────
# internal helpers
# ──────────────────────────────────────────────────────────────
def _price_at(df, ticker: str, target: dt.date) -> float | None:
    """
    Return the close-price for *ticker* on (or before) *target*.
    If no data yet, or DataFrame is empty, returns None.
    """
    if df.empty or "ticker" not in df.columns:
        return None

    sub = df[(df["ticker"] == ticker) & (df["date"] <= target.isoformat())]
    if sub.empty:
        return None
    return float(sub.iloc[-1]["close_gbp"])


# ──────────────────────────────────────────────────────────────
# public: collapse a group portfolio by ticker
# ──────────────────────────────────────────────────────────────
def aggregate_by_ticker(group_portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collapse *group portfolio* down to one row per ticker, enriched with:
        • last_price_gbp, last_price_date
        • change_7d_pct, change_30d_pct
    """
    # ----- 1. aggregate units / MV ------------------------------------------
    agg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: dict(
            ticker="",
            name="",
            units=0.0,
            market_value_gbp=0.0,
            gain_gbp=0.0,
        )
    )

    for acct in group_portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            row = agg[h["ticker"]]
            row["ticker"] = h["ticker"]
            row["name"] = h.get("name", h["ticker"])
            row["units"] += h.get("units", 0.0)
            row["market_value_gbp"] += h.get("market_value_gbp", 0.0)
            row["gain_gbp"] += h.get("unrealized_gain_gbp", 0.0)

    if not agg:
        return []

    tickers = sorted(agg.keys())

    # ----- 2. pull fresh prices ---------------------------------------------
    run_all_tickers(tickers)
    latest = get_latest_closing_prices()          # {ticker: price}

    today = dt.date.today()
    d7, d30 = today - dt.timedelta(days=7), today - dt.timedelta(days=30)

    ts_df = load_prices_for_tickers(tickers)      # may be empty on first run

    # ----- 3. enrich rows ----------------------------------------------------
    for tkr, row in agg.items():
        last_p = latest.get(tkr)
        row["last_price_gbp"] = last_p
        row["last_price_date"] = today.isoformat()

        p7 = _price_at(ts_df, tkr, d7)
        p30 = _price_at(ts_df, tkr, d30)

        row["change_7d_pct"] = (
            None
            if p7 in (None, 0) or last_p is None
            else (last_p - p7) / p7 * 100
        )
        row["change_30d_pct"] = (
            None
            if p30 in (None, 0) or last_p is None
            else (last_p - p30) / p30 * 100
        )

    # ----- 4. sorted list ----------------------------------------------------
    return sorted(agg.values(), key=lambda r: r["market_value_gbp"], reverse=True)
