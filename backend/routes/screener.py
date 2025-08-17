from __future__ import annotations

"""API route for basic stock screening based on valuation metrics."""

from typing import List

import hashlib

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from backend.screener import Fundamentals, screen
from backend.utils import page_cache

router = APIRouter(prefix="/screener", tags=["screener"])

SCREENER_TTL = 900  # seconds


@router.get("/", response_model=List[Fundamentals])
async def screener(
    background_tasks: BackgroundTasks,
    tickers: str = Query(..., description="Comma-separated list of tickers"),
    peg_max: float | None = Query(None),
    pe_max: float | None = Query(None),
    de_max: float | None = Query(None),
    fcf_min: float | None = Query(None),
    pb_max: float | None = Query(None),
    ps_max: float | None = Query(None),
    pc_max: float | None = Query(None),
    pfcf_max: float | None = Query(None),
    pebitda_max: float | None = Query(None),
    ev_ebitda_max: float | None = Query(None),
    ev_revenue_max: float | None = Query(None),
):
    """Return tickers that meet the supplied screening criteria."""

    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers supplied")

    params = (
        f"{','.join(symbols)}|{peg_max}|{pe_max}|{de_max}|{fcf_min}|"
        f"{pb_max}|{ps_max}|{pc_max}|{pfcf_max}|{pebitda_max}|{ev_ebitda_max}|{ev_revenue_max}"
    )
    page = "screener_" + hashlib.sha1(params.encode()).hexdigest()
    page_cache.schedule_refresh(
        page,
        SCREENER_TTL,
        lambda symbols=symbols,
        peg_max=peg_max,
        pe_max=pe_max,
        de_max=de_max,
        fcf_min=fcf_min,
        pb_max=pb_max,
        ps_max=ps_max,
        pc_max=pc_max,
        pfcf_max=pfcf_max,
        pebitda_max=pebitda_max,
        ev_ebitda_max=ev_ebitda_max,
        ev_revenue_max=ev_revenue_max: [
            r.model_dump()
            for r in screen(
                symbols,
                peg_max=peg_max,
                pe_max=pe_max,
                de_max=de_max,
                fcf_min=fcf_min,
                pb_max=pb_max,
                ps_max=ps_max,
                pc_max=pc_max,
                pfcf_max=pfcf_max,
                pebitda_max=pebitda_max,
                ev_ebitda_max=ev_ebitda_max,
                ev_revenue_max=ev_revenue_max,
            )
        ],
    )
    if not page_cache.is_stale(page, SCREENER_TTL):
        cached = page_cache.load_cache(page)
        if cached is not None:
            return cached

    try:
        result = screen(
            symbols,
            peg_max=peg_max,
            pe_max=pe_max,
            de_max=de_max,
            fcf_min=fcf_min,
            pb_max=pb_max,
            ps_max=ps_max,
            pc_max=pc_max,
            pfcf_max=pfcf_max,
            pebitda_max=pebitda_max,
            ev_ebitda_max=ev_ebitda_max,
            ev_revenue_max=ev_revenue_max,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    payload = [r.model_dump() for r in result]
    background_tasks.add_task(page_cache.save_cache, page, payload)
    return payload
