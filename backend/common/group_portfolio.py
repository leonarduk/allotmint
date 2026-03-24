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

from backend.common import portfolio as owner_portfolio
from backend.common.approvals import load_approvals
from backend.common.constants import (
    ACCOUNTS,
    HOLDINGS,
    OWNER,
)
from backend.common.holding_utils import enrich_holding
from backend.common.user_config import load_user_config
from backend.config import demo_identity as get_demo_identity
from backend.utils.pricing_dates import PricingDateCalculator

logger = logging.getLogger("group_portfolio")


def _trade_counts_for_owner(owner: str, today: dt.date) -> tuple[int, int]:
    """Return (trades_this_month, trades_remaining) for an owner."""

    try:
        trades = owner_portfolio.load_trades(owner)
    except FileNotFoundError:
        trades = []
    trades_this_month = 0
    for trade in trades:
        trade_date = owner_portfolio._parse_date(trade.get("date"))
        if trade_date and trade_date.year == today.year and trade_date.month == today.month:
            trades_this_month += 1

    try:
        user_cfg = load_user_config(owner)
        if isinstance(user_cfg, dict):
            max_monthly = int(user_cfg.get("max_trades_per_month") or 0)
        else:
            max_monthly = int(getattr(user_cfg, "max_trades_per_month", 0) or 0)
    except (FileNotFoundError, ValueError, TypeError):
        max_monthly = 0

    trades_remaining = max(0, max_monthly - trades_this_month)
    return trades_this_month, trades_remaining


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

    demo_identity = get_demo_identity()
    demo_lower = demo_identity.lower()
    demo_members = [o for o in owners if (o or "").lower() == demo_lower]
    if demo_lower == "demo" and demo_members:
        groups.append(
            {
                "slug": f"{demo_lower}-slug",
                "name": demo_identity.title(),
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
    portfolios_by_owner = {str(pf.get(OWNER, "")).lower(): pf for pf in portfolios_to_merge if pf.get(OWNER)}

    approvals_map: Dict[str, Dict[str, dt.date]] = {}
    user_cfg_map: Dict[str, Any] = {}
    for pf in portfolios_to_merge:
        owner = pf[OWNER]
        try:
            approvals_map[owner] = load_approvals(owner)
        except FileNotFoundError:
            approvals_map[owner] = {}
        try:
            user_cfg_map[owner] = load_user_config(owner)
        except FileNotFoundError:
            user_cfg_map[owner] = None

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

    subtotals_by_account_type: Dict[str, float] = {}
    for account in merged_accounts:
        account_type = str(account.get("account_type") or "").strip()
        if not account_type:
            continue
        subtotals_by_account_type[account_type] = subtotals_by_account_type.get(account_type, 0.0) + float(
            account.get("value_estimate_gbp") or 0.0
        )

    members_summary: List[Dict[str, Any]] = []
    for owner in grp.get("members", []):
        owner_key = str(owner or "").lower()
        owner_pf = portfolios_by_owner.get(owner_key)
        if owner_pf is None:
            members_summary.append(
                {
                    "owner": owner,
                    "total_value_estimate_gbp": 0.0,
                    "total_value_estimate_currency": None,
                    "trades_this_month": 0,
                    "trades_remaining": 0,
                }
            )
            continue

        try:
            owner_details = owner_portfolio.build_owner_portfolio(owner, pricing_date=pricing_date)
        except FileNotFoundError:
            trades_this_month, trades_remaining = _trade_counts_for_owner(owner, today)
            owner_total = sum(
                float(account.get("value_estimate_gbp") or 0.0)
                for account in merged_accounts
                if str(account.get(OWNER) or "").lower() == owner_key
            )
            owner_details = {
                "total_value_estimate_gbp": owner_total,
                "total_value_estimate_currency": "GBP" if owner_total else None,
                "trades_this_month": trades_this_month,
                "trades_remaining": trades_remaining,
            }

        members_summary.append(
            {
                "owner": owner,
                "total_value_estimate_gbp": float(owner_details.get("total_value_estimate_gbp") or 0.0),
                "total_value_estimate_currency": owner_details.get("total_value_estimate_currency"),
                "trades_this_month": int(owner_details.get("trades_this_month") or 0),
                "trades_remaining": int(owner_details.get("trades_remaining") or 0),
            }
        )

    return {
        "slug": slug,
        "name": grp["name"],
        "members": grp.get("members", []),
        "as_of": pricing_date.isoformat(),
        "total_value_estimate_gbp": total_value,
        "members_summary": members_summary,
        "subtotals_by_account_type": subtotals_by_account_type,
        ACCOUNTS: merged_accounts,
    }
