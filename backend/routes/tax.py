from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.common.tax import harvest_losses
from backend.common.allowances import (
    current_tax_year,
    remaining_allowances,
)

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
async def allowances(
    owner: str | None = Query(None),
    current_user: str = Depends(get_current_user),
) -> Dict[str, Dict[str, float]]:
    """Return remaining ISA and pension allowances for ``owner``.

    If ``owner`` is not provided the currently authenticated user is used.
    The response contains ``used``, ``limit`` and ``remaining`` totals for
    each supported account type in the current UK tax year.
    """

    if owner is None:
        owner = current_user
    tax_year = current_tax_year()
    data = remaining_allowances(owner, tax_year)
    return {"owner": owner, "tax_year": tax_year, "allowances": data}
