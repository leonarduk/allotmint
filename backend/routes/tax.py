from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from backend.auth import get_active_user
from backend.common.tax import harvest_losses
from backend.common.allowances import (
    current_tax_year,
    remaining_allowances,
)
from backend.common import data_loader
from backend.config import demo_identity

router = APIRouter(prefix="/tax", tags=["tax"])


class Position(BaseModel):
    ticker: str
    basis: float
    price: float


class HarvestRequest(BaseModel):
    positions: List[Position]
    threshold: float | None = None


@router.post("/harvest")
async def harvest(req: HarvestRequest) -> dict:
    trades = harvest_losses([p.model_dump() for p in req.positions], req.threshold or 0.0)
    return {"trades": trades}


@router.get("/allowances")
async def allowances(request: Request, owner: str | None = Query(None)) -> dict:
    """Return remaining ISA and pension allowances for ``owner``.

    When auth is enabled and ``owner`` is not provided, the authenticated user
    is used.  When auth is disabled, the configured demo account is used.
    """
    active_user = await get_active_user(request)
    if owner is None:
        if active_user is not None:
            owner = active_user
        else:
            aliases = data_loader.demo_identity_aliases()
            preferred = next((a for a in aliases if a.lower() == "demo"), None)
            owner = preferred or (aliases[0] if aliases else demo_identity())
    tax_year = current_tax_year()
    data = remaining_allowances(owner, tax_year)
    return {"owner": owner, "tax_year": tax_year, "allowances": data}
