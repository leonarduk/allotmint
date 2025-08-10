from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from backend.timeseries.cache import (
    EXPECTED_COLS,
    _ensure_schema,
    meta_timeseries_cache_path,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])


def _load_timeseries(ticker: str, exchange: str) -> pd.DataFrame:
    path = meta_timeseries_cache_path(ticker, exchange)
    if path.exists():
        try:
            return _ensure_schema(pd.read_parquet(path))
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail=str(exc))
    return pd.DataFrame(columns=EXPECTED_COLS)


@router.get("/edit")
async def get_timeseries_edit(
    ticker: str = Query(...), exchange: str = Query("L")
) -> JSONResponse:
    df = _load_timeseries(ticker, exchange)
    if not df.empty:
        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return JSONResponse(df.to_dict(orient="records"))


@router.post("/edit")
async def post_timeseries_edit(
    request: Request, ticker: str = Query(...), exchange: str = Query("L")
) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    try:
        if "text/csv" in content_type:
            body = await request.body()
            df = pd.read_csv(io.StringIO(body.decode()))
        else:
            payload = await request.json()
            if isinstance(payload, list):
                df = pd.DataFrame(payload)
            else:
                raise ValueError("JSON payload must be a list of records")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    df = _ensure_schema(df)
    if "Ticker" not in df.columns or df["Ticker"].isna().all():
        df["Ticker"] = ticker
    if "Source" not in df.columns or df["Source"].isna().all():
        df["Source"] = "Manual"

    path = meta_timeseries_cache_path(ticker, exchange)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return JSONResponse({"status": "ok", "rows": len(df)})
