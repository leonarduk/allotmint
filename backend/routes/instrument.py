"""
/instrument router shared by every deployment target.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query
from backend.common.portfolio_utils import (
    aggregate_by_ticker,
    list_all_unique_tickers,
)
from backend.common.group_portfolio import list_groups
from backend.utils.cache import load_meta_timeseries

router = APIRouter(tags=["instrument"])
log = logging.getLogger("routes.instrument")


def _snapshot_row(ticker: str) -> dict | None:
    ticker = ticker.upper()
    for pf in list_groups():
        for row in aggregate_by_ticker(pf):
            if row["ticker"] == ticker:
                return row
    return None


@router.get("/instrument")
async def instrument(
    ticker: str = Query(..., description="Exact ticker, e.g. XDEV.L"),
    days: int = Query(365, ge=30, le=1825, description="Look-back window"),
):
    ticker = ticker.upper()

    if ticker not in list_all_unique_tickers():
        raise HTTPException(status_code=404, detail="Ticker not found in portfolios")

    row = _snapshot_row(ticker)
    if not row:
        raise HTTPException(status_code=404, detail="Ticker held nowhere")

    try:
        ts_df = load_meta_timeseries(ticker, "L", days)
        timeseries: List[dict] = [
            {"Date": str(r.Date), "Close": float(r.Close)}
            for r in ts_df[["Date", "Close"]].itertuples(index=False)
        ]
    except Exception as exc:
        log.warning("Timeseries fetch failed for %s: %s", ticker, exc)
        timeseries = []

    return {**row, "timeseries": timeseries}
