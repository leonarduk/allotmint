from __future__ import annotations

import io
import logging

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from backend.common import instrument_api
from backend.timeseries.cache import (
    EXPECTED_COLS,
    _ensure_schema,
    meta_timeseries_cache_path,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])
logger = logging.getLogger("routes.timeseries")


def _resolve_ticker_exchange(ticker: str, exchange: str | None) -> tuple[str, str]:
    t = (ticker or "").upper()
    if not t:
        raise HTTPException(status_code=400, detail="Ticker is required")

    if exchange:
        sym = t.split(".", 1)[0]
        ex = exchange.upper()
        logger.debug("Resolved %s.%s (provided exchange)", sym, ex)
        return sym, ex

    if "." in t:
        sym, ex = t.split(".", 1)
        logger.debug("Resolved %s.%s (provided exchange)", sym, ex)
        return sym, ex

    resolved = instrument_api._resolve_full_ticker(
        t, instrument_api._LATEST_PRICES
    )
    if not resolved:
        logger.debug("Could not infer exchange for %s", t)
        raise HTTPException(
            status_code=400, detail=f"Exchange not provided and could not be inferred for {ticker}"
        )
    sym, ex = resolved
    logger.debug("Resolved %s.%s (inferred exchange)", sym, ex)
    return sym, ex


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
    ticker: str = Query(...), exchange: str | None = Query(None)
) -> JSONResponse:
    ticker, exchange = _resolve_ticker_exchange(ticker, exchange)
    df = _load_timeseries(ticker, exchange)
    if not df.empty:
        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return JSONResponse(df.to_dict(orient="records"))


@router.post("/edit")
async def post_timeseries_edit(
    request: Request, ticker: str = Query(...), exchange: str | None = Query(None)
) -> JSONResponse:
    ticker, exchange = _resolve_ticker_exchange(ticker, exchange)
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
