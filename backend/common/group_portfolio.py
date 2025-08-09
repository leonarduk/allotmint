# backend/common/group_portfolio.py
from __future__ import annotations

"""
Virtual "group portfolio" builder.

- list_groups()                -> synthetic list generated from owners
- build_group_portfolio(slug)  -> merge owners -> one portfolio dict
"""

import datetime as dt
import json
import logging
from typing import Any, Dict, List

from backend.common.constants import (
    OWNER,
    ACCOUNTS,
    HOLDINGS,
)
from backend.common.holding_utils import enrich_holding

logger = logging.getLogger("group_portfolio")


# ───────────────────────── groups list ──────────────────────────
def list_groups() -> List[Dict[str, Any]]:
    """
    Build a default set of groups based on the owners that exist.
    - "all"      - every owner
    - "adults"   - lucy + steve
    - "children" - alex + joe
    """
    from backend.common.portfolio_loader import list_portfolios  # local import avoids cycles

    owners = sorted({pf.get("owner") for pf in list_portfolios() if pf.get("owner")})

    return [
        {
            "slug": "all",
            "name": "All owners combined",
            "members": owners,
        },
        {
            "slug": "adults",
            "name": "Adults",
            "members": [o for o in owners if (o or "").lower() in {"lucy", "steve"}],
        },
        {
            "slug": "children",
            "name": "Children",
            "members": [o for o in owners if (o or "").lower() in {"alex", "joe"}],
        },
    ]


# ───────────────────────── core builder ─────────────────────────
def build_group_portfolio(slug: str) -> Dict[str, Any]:
    groups = {g["slug"]: g for g in list_groups()}
    grp = groups.get(slug)
    if not grp:
        raise ValueError(f"Unknown group slug: {slug!r}")

    wanted = {o.lower() for o in grp["members"]}

    # Get portfolios to merge (raw portfolios; we will enrich here)
    from backend.common.portfolio_loader import list_portfolios  # local import avoids cycles

    portfolios_to_merge = [
        pf for pf in list_portfolios() if (pf.get(OWNER, "") or "").lower() in wanted
    ]

    today = dt.date.today()
    price_cache: dict[str, float] = {}

    merged_accounts: List[Dict[str, Any]] = []

    for pf in portfolios_to_merge:
        for acct in pf.get(ACCOUNTS, []):
            owner = pf[OWNER]
            acct_copy = dict(acct)
            acct_copy[OWNER] = owner

            holdings = acct_copy.get(HOLDINGS, [])
            acct_copy[HOLDINGS] = [
                enrich_holding(h, today, price_cache) for h in holdings
            ]

            # compute account value in GBP for summary totals
            val_gbp = sum(
                float(h.get("market_value_gbp") or 0.0)
                for h in acct_copy[HOLDINGS]
            )
            acct_copy["value_estimate_gbp"] = val_gbp

            merged_accounts.append(acct_copy)

    # Place accounts with actual holdings first to keep downstream consumers
    # (and tests) simple. Some metadata-only accounts like pension forecasts
    # contain no holdings which previously surfaced as the first account and
    # triggered index errors.
    merged_accounts.sort(key=lambda a: len(a.get(HOLDINGS, [])), reverse=True)

    total_value = sum(float(a.get("value_estimate_gbp") or 0.0) for a in merged_accounts)

    return {
        "slug": slug,
        "name": grp["name"],
        "members": grp.get("members", []),
        "as_of": today.isoformat(),
        "total_value_estimate_gbp": total_value,
        ACCOUNTS: merged_accounts,
    }
