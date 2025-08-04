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
from backend.common.portfolio_utils import aggregate_by_ticker

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
    try:
        return build_owner_portfolio(owner)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")


@router.get("/portfolio-group/{slug}")
async def portfolio_group(slug: str):
    try:
        return build_group_portfolio(slug)
    except KeyError:
        raise HTTPException(status_code=404, detail="Group not found")


# ──────────────────────────────────────────────────────────────
# Group-level aggregation
# ──────────────────────────────────────────────────────────────
@router.get("/portfolio-group/{slug}/instruments")
async def group_instruments(slug: str):
    gp = build_group_portfolio(slug)
    return aggregate_by_ticker(gp)
