# backend/common/group_portfolio.py
from __future__ import annotations

"""
Virtual "group portfolio" builder.

- list_groups()                -> synthetic list generated from owners
- build_group_portfolio(slug)  -> merge owners -> one portfolio dict
"""

import datetime as dt
import logging
from datetime import date
from typing import Any, Dict, List

from backend.common.approvals import load_approvals
from backend.common.constants import (
    ACCOUNTS,
    HOLDINGS,
    OWNER,
)
from backend.common.holding_utils import enrich_holding
from backend.common.user_config import load_user_config
from backend.utils.pricing_dates import PricingDateCalculator

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

    groups = [
        {
            "slug": "all",
            "name": "At a glance",
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

    demo_members = [o for o in owners if (o or "").lower() == "demo"]
    if demo_members:
        groups.append(
            {
                "slug": "demo-slug",
                "name": "Demo",
                "members": demo_members,
            }
        )

    return groups


# ───────────────────────── core builder ─────────────────────────
def build_group_portfolio(slug: str, *, pricing_date: date | None = None) -> Dict[str, Any]:
    groups = {g["slug"]: g for g in list_groups()}
    grp = groups.get(slug)
    if not grp:
        raise ValueError(f"Unknown group slug: {slug!r}")

    wanted = {o.lower() for o in grp["members"]}

    # Get portfolios to merge (raw portfolios; we will enrich here)
    from backend.common.portfolio_loader import list_portfolios  # local import avoids cycles

    portfolios_to_merge = [pf for pf in list_portfolios() if (pf.get(OWNER, "") or "").lower() in wanted]

    approvals_map = {pf[OWNER]: load_approvals(pf[OWNER]) for pf in portfolios_to_merge}
    user_cfg_map = {pf[OWNER]: load_user_config(pf[OWNER]) for pf in portfolios_to_merge}

    calc = PricingDateCalculator(reporting_date=pricing_date)
    today = calc.today
    pricing_date = calc.reporting_date
    price_cache: dict[str, float] = {}

    merged_accounts: List[Dict[str, Any]] = []

    for pf in portfolios_to_merge:
        for acct in pf.get(ACCOUNTS, []):
            owner = pf[OWNER]
            acct_copy = dict(acct)
            acct_copy[OWNER] = owner

            holdings = acct_copy.get(HOLDINGS, [])
            acct_copy[HOLDINGS] = [
                enrich_holding(
                    h,
                    today,
                    price_cache,
                    approvals_map.get(owner),
                    user_cfg_map.get(owner),
                    calc=calc,
                )
                for h in holdings
            ]

            # compute account value in GBP for summary totals
            val_gbp = sum(float(h.get("market_value_gbp") or 0.0) for h in acct_copy[HOLDINGS])
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
        "as_of": pricing_date.isoformat(),
        "total_value_estimate_gbp": total_value,
        ACCOUNTS: merged_accounts,
    }
