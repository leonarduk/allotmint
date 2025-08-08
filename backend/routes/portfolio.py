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

from backend.common import (
    data_loader,
    group_portfolio,
    portfolio as portfolio_mod,
    portfolio_utils,
    prices,
    instrument_api,
)

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
    return data_loader.list_plots()


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
    return group_portfolio.list_groups()


# ──────────────────────────────────────────────────────────────
# Owner / group portfolios
# ──────────────────────────────────────────────────────────────
@router.get("/portfolio/{owner}")
async def portfolio(owner: str):
    try:
        return portfolio_mod.build_owner_portfolio(owner)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")


@router.get("/portfolio-group/{slug}")
async def portfolio_group(slug: str):
    try:
        return group_portfolio.build_group_portfolio(slug)
    except Exception as e:
        log.warning(f"Failed to load group {slug}: {e}")
        raise HTTPException(status_code=404, detail="Group not found")


# ──────────────────────────────────────────────────────────────
# Group-level aggregation
# ──────────────────────────────────────────────────────────────
@router.get("/portfolio-group/{slug}/instruments")
async def group_instruments(slug: str):
    gp = group_portfolio.build_group_portfolio(slug)
    return portfolio_utils.aggregate_by_ticker(gp)


@router.get("/account/{owner}/{account}")
async def get_account(owner: str, account: str):
    try:
        return data_loader.load_account(owner, account.lower())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found")


@router.get("/portfolio-group/{slug}/instrument/{ticker}")
async def instrument_detail(slug: str, ticker: str):
    try:
        prices_list = instrument_api.timeseries_for_ticker(ticker)
        if not prices_list:
            raise ValueError("no prices")
        positions_list = instrument_api.positions_for_ticker(slug, ticker)
    except Exception:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return {"prices": prices_list, "positions": positions_list}

@router.api_route("/prices/refresh", methods=["GET", "POST"])
async def refresh_prices():
    log.info("🔄 Refreshing prices via /prices/refresh")
    result = prices.refresh_prices()
    return {"status": "ok", **result}
