"""
Owners / groups / portfolio endpoints (shared).

    - /owners
    - /groups
    - /portfolio/{owner}
    - /portfolio-group/{slug}
    - /portfolio-group/{slug}/instruments
"""

from __future__ import annotations

import logging
from datetime import date
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
    risk,
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
          ...
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
          ...
        ]
    """
    return group_portfolio.list_groups()


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
        return portfolio_mod.build_owner_portfolio(owner)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")


@router.get("/performance/{owner}")
async def performance(owner: str, days: int = 365):
    """Return portfolio performance metrics for ``owner``."""
    try:
        result = portfolio_utils.compute_owner_performance(owner, days=days)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    return {"owner": owner, **result}


@router.get("/var/{owner}")
async def portfolio_var(owner: str, days: int = 365, confidence: float = 0.95):
    """Return historical-simulation VaR for ``owner``.

    Parameters
    ----------
    days:
        Length of the historical window used for returns. Must be positive.
        VaR is reported for 1-day and 10-day horizons.
    confidence:
        Quantile for losses in (0, 1). Defaults to 0.95 (95 %); 0.99 is
        also common.

    Returns a JSON object ``{"owner": owner, "as_of": <today>, "var": {...}}``.
    Raises 404 if the owner does not exist and 400 for invalid parameters.
    """

    try:
        var = risk.compute_portfolio_var(owner, days=days, confidence=confidence)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"owner": owner, "as_of": date.today().isoformat(), "var": var}


@router.get("/portfolio-group/{slug}")
async def portfolio_group(slug: str):
    """Return the aggregated portfolio for a group.

    Groups are defined in configuration and simply reference a list of owner
    slugs. The aggregation combines holdings across all members.
    """

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
    """Return holdings for the group aggregated by ticker."""

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
    """Rebuild the in-memory price snapshot used by portfolio lookups."""

    log.info("Refreshing prices via /prices/refresh")
    result = prices.refresh_prices()
    return {"status": "ok", **result}
