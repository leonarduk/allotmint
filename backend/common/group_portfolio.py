from __future__ import annotations

"""
Group portfolio aggregation for AllotMint.

Groups:
  family   -> stephen, lucy, alex, joe
  adults   -> stephen, lucy
  children -> alex, joe
"""

import datetime as dt
from typing import Dict, List, Any, Optional

from backend.common.portfolio import build_owner_portfolio


GROUP_DEFS: Dict[str, List[str]] = {
    "family":   ["stephen", "lucy", "alex", "joe"],
    "adults":   ["stephen", "lucy"],
    "children": ["alex", "joe"],
}


def list_groups() -> List[Dict[str, Any]]:
    """Return groups + member owner IDs."""
    return [{"group": g, "members": m} for g, m in GROUP_DEFS.items()]


def build_group_portfolio(group: str, env: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate member portfolios into a group view.
    Returns:
      {
        group: "family",
        as_of: "...",
        members: ["stephen", "lucy", ...],
        total_value_estimate_gbp: float,
        members_summary: [
          {owner, total_value_estimate_gbp, trades_this_month, trades_remaining}
        ],
        subtotals_by_account_type: { "ISA": float, "SIPP": float, "DB": float }
      }
    """
    group = group.lower()
    if group not in GROUP_DEFS:
        raise KeyError(f"Unknown group '{group}'")

    members = GROUP_DEFS[group]
    as_of = dt.date.today().isoformat()

    group_total = 0.0
    members_summary = []
    acct_subtotals: Dict[str, float] = {}

    for owner in members:
        p = build_owner_portfolio(owner, env=env)
        group_total += p["total_value_estimate_gbp"]
        members_summary.append({
            "owner": owner,
            "total_value_estimate_gbp": p["total_value_estimate_gbp"],
            "trades_this_month": p["trades_this_month"],
            "trades_remaining": p["trades_remaining"],
        })
        # accumulate by account type
        for acct in p["accounts"]:
            acct_type = str(acct.get("account_type", "UNKNOWN")).upper()
            acct_subtotals[acct_type] = acct_subtotals.get(acct_type, 0.0) + float(acct["value_estimate_gbp"])

    return {
        "group": group,
        "as_of": as_of,
        "members": members,
        "total_value_estimate_gbp": group_total,
        "members_summary": members_summary,
        "subtotals_by_account_type": acct_subtotals,
    }
