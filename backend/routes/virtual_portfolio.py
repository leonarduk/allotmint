from __future__ import annotations

"""Endpoints for managing virtual portfolios."""

from typing import List

from fastapi import APIRouter, HTTPException

from backend.common.virtual_portfolio import (
    VirtualPortfolio,
    VirtualPortfolioSummary,
    delete_virtual_portfolio,
    list_virtual_portfolio_metadata,
    load_virtual_portfolio,
    save_virtual_portfolio,
)

router = APIRouter(tags=["virtual-portfolios"])


@router.get("/virtual-portfolios", response_model=List[VirtualPortfolioSummary])
async def list_virtual_portfolios():
    """Return metadata for all virtual portfolios."""
    return list_virtual_portfolio_metadata()


@router.get("/virtual-portfolios/{vp_id}", response_model=VirtualPortfolio)
async def get_virtual_portfolio(vp_id: str):
    """Load a full virtual portfolio."""
    vp = load_virtual_portfolio(vp_id)
    if not vp:
        raise HTTPException(status_code=404, detail="Virtual portfolio not found")
    return vp


@router.post("/virtual-portfolios", response_model=VirtualPortfolio)
async def create_or_update_virtual_portfolio(vp: VirtualPortfolio):
    """Create or update a virtual portfolio."""
    return save_virtual_portfolio(vp)


@router.delete("/virtual-portfolios/{vp_id}")
async def delete_virtual_portfolio_route(vp_id: str):
    """Remove a virtual portfolio."""
    delete_virtual_portfolio(vp_id)
    return {"status": "ok"}
