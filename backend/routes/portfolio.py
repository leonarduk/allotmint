"""
Owners / groups / portfolio endpoints (shared).

    • /owners
    • /groups
    • /portfolio/{owner}
    • /portfolio-group/{slug}
    • /portfolio-group/{slug}/instruments
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.common.data_loader import list_plots, load_account
from backend.common.group_portfolio import (
    list_groups,
    build_group_portfolio,
)
from backend.common.portfolio import build_owner_portfolio
from backend.common.portfolio_utils import aggregate_by_ticker, refresh_snapshot_in_memory_from_timeseries, \
    _PRICE_SNAPSHOT

log = logging.getLogger("routes.portfolio")
router = APIRouter(tags=["portfolio"])


# ──────────────────────────────────────────────────────────────
# Pydantic models for validation
# ──────────────────────────────────────────────────────────────
class OwnerSummary(BaseModel):
    owner: str
    accounts: List[str]


class GroupSummary(BaseModel):
    slug: str
    name: str
    members: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Simple lists
# ──────────────────────────────────────────────────────────────
@router.get("/owners", response_model=List[OwnerSummary])
async def owners():
    """
    Returns
        [
          {"owner": "alex",  "accounts": ["isa", "sipp"]},
          {"owner": "joe",   "accounts": ["isa", "sipp"]},
          …
        ]
    """
    return list_plots()


@router.get("/groups", response_model=List[GroupSummary])
async def groups():
    """
    Returns
        [
          {"slug": "children", "name": "Children", "members": ["alex", "joe"]},
          {"slug": "adults",   "name": "Adults",   "members": ["lucy", "steve"]},
          …
        ]
    """
    return list_groups()


# ──────────────────────────────────────────────────────────────
# Owner / group portfolios
# ──────────────────────────────────────────────────────────────
@router.get("/portfolio/{owner}")
async def portfolio(owner: str):
    """Return the fully expanded portfolio for ``owner``.

    The helper function :func:`build_owner_portfolio` loads account data from
    disk, calculates current values and returns a nested structure describing
    the owner's holdings.
    """

    try:
        return build_owner_portfolio(owner)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")


@router.get("/portfolio-group/{slug}")
async def portfolio_group(slug: str):
    """Return the aggregated portfolio for a group.

    Groups are defined in configuration and simply reference a list of owner
    slugs. The aggregation combines holdings across all members.
    """

    try:
        return build_group_portfolio(slug)
    except Exception as e:
        log.warning(f"Failed to load group {slug}: {e}")
        raise HTTPException(status_code=404, detail="Group not found")


# ──────────────────────────────────────────────────────────────
# Group-level aggregation
# ──────────────────────────────────────────────────────────────
@router.get("/portfolio-group/{slug}/instruments")
async def group_instruments(slug: str):
    """Return holdings for the group aggregated by ticker."""

    gp = build_group_portfolio(slug)
    return aggregate_by_ticker(gp)

@router.api_route("/prices/refresh", methods=["GET", "POST"])
async def refresh_prices():
    """Rebuild the in-memory price snapshot used by portfolio lookups."""

    log.info("🔄 Refreshing prices via /prices/refresh")
    refresh_snapshot_in_memory_from_timeseries()
    return {"tickers": len(_PRICE_SNAPSHOT)}
