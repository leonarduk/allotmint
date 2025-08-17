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
    eps_min: float | None = Query(None),
    gross_margin_min: float | None = Query(None),
    operating_margin_min: float | None = Query(None),
    net_margin_min: float | None = Query(None),
    ebitda_margin_min: float | None = Query(None),
    roa_min: float | None = Query(None),
    roe_min: float | None = Query(None),
    roi_min: float | None = Query(None),
):
    """Return tickers that meet the supplied screening criteria."""

    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers supplied")

    params = (
        f"{','.join(symbols)}|{peg_max}|{pe_max}|{de_max}|{fcf_min}|"
        f"{eps_min}|{gross_margin_min}|{operating_margin_min}|{net_margin_min}|"
        f"{ebitda_margin_min}|{roa_min}|{roe_min}|{roi_min}"
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
        eps_min=eps_min,
        gross_margin_min=gross_margin_min,
        operating_margin_min=operating_margin_min,
        net_margin_min=net_margin_min,
        ebitda_margin_min=ebitda_margin_min,
        roa_min=roa_min,
        roe_min=roe_min,
        roi_min=roi_min: [
            r.model_dump()
            for r in screen(
                symbols,
                peg_max=peg_max,
                pe_max=pe_max,
                de_max=de_max,
                fcf_min=fcf_min,
                eps_min=eps_min,
                gross_margin_min=gross_margin_min,
                operating_margin_min=operating_margin_min,
                net_margin_min=net_margin_min,
                ebitda_margin_min=ebitda_margin_min,
                roa_min=roa_min,
                roe_min=roe_min,
                roi_min=roi_min,
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
            eps_min=eps_min,
            gross_margin_min=gross_margin_min,
            operating_margin_min=operating_margin_min,
            net_margin_min=net_margin_min,
            ebitda_margin_min=ebitda_margin_min,
            roa_min=roa_min,
            roe_min=roe_min,
            roi_min=roi_min,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    payload = [r.model_dump() for r in result]
    background_tasks.add_task(page_cache.save_cache, page, payload)
    return payload
