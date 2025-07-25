# backend/common/portfolio_utils.py
"""
Helper functions that aggregate holdings for owner/group portfolios.
"""

from collections import defaultdict
from typing import Dict, List, Any


def aggregate_by_ticker(group_portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collapse all holdings inside a *group portfolio* down to one row per ticker.

    Returns a list sorted by market value desc.  Each dict contains:
    ticker, name, units, market_value_gbp, gain_gbp
    """
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

    return sorted(agg.values(), key=lambda r: r["market_value_gbp"], reverse=True)
