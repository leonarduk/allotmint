# backend/routes/movers.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.common.instrument_api import top_movers

router = APIRouter(tags=["movers"])

_ALLOWED_DAYS = {1, 7, 30, 90, 365}


@router.get("/movers")
def get_movers(
    tickers: str = Query(..., description="Comma-separated tickers"),
    days: int = Query(1, description="Lookback window"),
    limit: int = Query(10, description="Max results per side"),
):
    if days not in _ALLOWED_DAYS:
        raise HTTPException(status_code=400, detail="Invalid days")
    tlist = [t.strip() for t in tickers.split(",") if t.strip()]
    if not tlist:
        raise HTTPException(status_code=400, detail="No tickers provided")
    return top_movers(tlist, days, limit)
