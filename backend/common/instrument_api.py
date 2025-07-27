# backend/common/instrument_api.py
from __future__ import annotations
import datetime as dt
from typing import List, Dict, Any

from backend.timeseries.fetch_timeseries import run_all_tickers
from backend.common.prices import load_prices_for_tickers
from backend.common.group_portfolio import build_group_portfolio


def timeseries_for_ticker(ticker: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Last *days* of close prices for ticker – empty list if we have no data.
    """
    run_all_tickers([ticker])
    df = load_prices_for_tickers([ticker])

    # ── guard against empty / malformed DF ────────────────────────────────
    if df.empty or {"date", "close_gbp"} - set(df.columns):
        return []

    cutoff = dt.date.today() - dt.timedelta(days=days)
    df = df[df["date"] >= cutoff.isoformat()]

    return [
        {"date": r["date"], "close_gbp": float(r["close_gbp"])}
        for _, r in df.iterrows()
    ]


def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    gp = build_group_portfolio(group_slug)
    rows: list[Dict[str, Any]] = []

    for owner in gp["members"]:
        for acct in gp["accounts"]:
            for h in acct["holdings"]:
                if h["ticker"] == ticker and h.get("units", 0):
                    rows.append(
                        {
                            "owner": owner,
                            "units": h["units"],
                            "market_value_gbp": h["market_value_gbp"],
                            "cost_basis_gbp": h.get("cost_basis_gbp", 0),
                            "unrealised_gain_gbp": h.get("unrealised_gain_gbp", 0),
                        }
                    )
    return rows
