# backend/routes/rebalance.py
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.common.rebalance import suggest_trades

router = APIRouter(tags=["rebalance"])


class RebalanceRequest(BaseModel):
    actual: Dict[str, float]
    target: Dict[str, float]


class TradeSuggestion(BaseModel):
    ticker: str
    action: str
    amount: float


@router.post("/rebalance", response_model=List[TradeSuggestion])
def rebalance(req: RebalanceRequest) -> List[TradeSuggestion]:
    try:
        return suggest_trades(req.actual, req.target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
