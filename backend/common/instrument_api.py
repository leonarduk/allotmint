# backend/common/instrument_api.py
from __future__ import annotations
import datetime as dt
from pathlib import Path
from typing import Dict, List, Any

from backend.timeseries.fetch_timeseries import run_all_tickers
from backend.common.prices import load_prices_for_tickers
from backend.common.group_portfolio import build_group_portfolio


def timeseries_for_ticker(ticker: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Return last *days* closing prices (date, close_gbp) for ticker.
    """
    run_all_tickers([ticker])
    df = load_prices_for_tickers([ticker])
    cutoff = dt.date.today() - dt.timedelta(days=days)
    df = df[df["date"] >= cutoff.isoformat()]
    return [
        {"date": r["date"], "close_gbp": float(r["close_gbp"])}
        for _, r in df.iterrows()
    ]


def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    """
    Return one dict per owner holding *ticker* in the group:
    owner, units, market_value_gbp, cost_basis_gbp, unrealised_gain_gbp.
    """
    gp = build_group_portfolio(group_slug)
    rows = []
    for owner in gp["members"]:
        for acct in gp["accounts"]:
            for h in acct["holdings"]:
                if h["ticker"] == ticker and h["units"]:
                    rows.append(
                        {
                            "owner": owner,
                            "units": h["units"],
                            "market_value_gbp": h["market_value_gbp"],
                            "cost_basis_gbp": h.get("cost_basis_gbp", 0),
                            "unrealised_gain_gbp": h.get(
                                "unrealised_gain_gbp", 0
                            ),
                        }
                    )
    return rows
