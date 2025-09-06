from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.common.tax import harvest_losses

router = APIRouter(prefix="/tax", tags=["tax"])


class Position(BaseModel):
    ticker: str
    basis: float
    price: float


class HarvestRequest(BaseModel):
    positions: List[Position]
    threshold: float | None = None


@router.post("/harvest")
async def harvest(req: HarvestRequest, current_user: str = Depends(get_current_user)) -> dict:
    del current_user
    trades = harvest_losses(
        [p.model_dump() for p in req.positions], req.threshold or 0.0
    )
    return {"trades": trades}
