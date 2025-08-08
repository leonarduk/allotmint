from datetime import date, timedelta

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import (
    apply_scaling,
    get_scaling_override,
    handle_timeseries_response,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])

@router.get("/meta", response_class=HTMLResponse)
async def get_meta_timeseries(
    ticker: str = Query(...),
    exchange: str = Query("L"),
    days: int = Query(365, ge=30, le=3650),
    format: str = Query("html", regex="^(html|json|csv)$"),
    scaling: float = Query(1.0, ge=0.00001, le=1_000_000),
):
    start_date = date.today() - timedelta(days=days)
    end_date = date.today() - timedelta(days=1)

    try:
        df = load_meta_timeseries_range(
            ticker, exchange, start_date=start_date, end_date=end_date
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        raise HTTPException(
            status_code=404, detail=f"No data found for {ticker}.{exchange}"
        )

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    scale = get_scaling_override(ticker, exchange, scaling)
    df = apply_scaling(df, scale)

    metadata = {
        "ticker": f"{ticker}.{exchange}",
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "scaling": scale,
    }
    title = f"{ticker}.{exchange} Price History"
    subtitle = f"{start_date} to {end_date}"

    return handle_timeseries_response(
        df, format, title, subtitle, metadata=metadata
    )
