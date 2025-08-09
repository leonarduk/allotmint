from __future__ import annotations

"""API route for basic stock screening based on valuation metrics."""

from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.screener import Fundamentals, screen

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("/", response_model=List[Fundamentals])
async def screener(
    tickers: str = Query(..., description="Comma-separated list of tickers"),
    peg_max: float | None = Query(None),
    pe_max: float | None = Query(None),
    de_max: float | None = Query(None),
    fcf_min: float | None = Query(None),
):
    """Return tickers that meet the supplied screening criteria."""

    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers supplied")

    try:
        return screen(
            symbols,
            peg_max=peg_max,
            pe_max=pe_max,
            de_max=de_max,
            fcf_min=fcf_min,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
