from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import pandas as pd
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from backend.common import instrument_api
from backend.common.errors import InternalServiceError, ValidationFailure
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import (
    EXPECTED_COLS,
    _ensure_schema,
    _s3_client,
    _split_s3_cache_uri,
    has_cached_meta_timeseries,
    invalidate_s3_cache_metadata,
    meta_timeseries_cache_path,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])
logger = logging.getLogger(__name__)


def _resolve_ticker_exchange(ticker: str, exchange: str | None) -> tuple[str, str]:
    t = (ticker or "").upper()
    if not t:
        raise ValidationFailure("Ticker is required", extra={"field": "ticker"})

    if exchange:
        sym = t.split(".", 1)[0]
        ex = exchange.upper()
        logger.debug("Resolved %s.%s (provided exchange)", sanitise_log_value(sym), sanitise_log_value(ex))
        return sym, ex

    if "." in t:
        sym, ex = t.split(".", 1)
        logger.debug("Resolved %s.%s (provided exchange)", sanitise_log_value(sym), sanitise_log_value(ex))
        return sym, ex

    resolved = instrument_api._resolve_full_ticker(t, instrument_api._LATEST_PRICES)
    if not resolved:
        logger.debug("Could not infer exchange for %s", sanitise_log_value(t))
        raise ValidationFailure(
            f"Exchange not provided and could not be inferred for {ticker}",
            extra={"field": "exchange", "ticker": ticker},
        )
    sym, ex = resolved
    logger.debug("Resolved %s.%s (inferred exchange)", sanitise_log_value(sym), sanitise_log_value(ex))
    return sym, ex


def _load_timeseries(ticker: str, exchange: str) -> pd.DataFrame:
    cache = meta_timeseries_cache_path(ticker, exchange)
    exists = _s3_object_exists_strict(cache) if cache.startswith("s3://") else Path(cache).exists()
    if exists:
        try:
            return _ensure_schema(pd.read_parquet(cache))
        except Exception as exc:  # pragma: no cover - defensive
            raise InternalServiceError(
                f"Failed to load cached timeseries for {ticker}.{exchange}",
                extra={"ticker": ticker, "exchange": exchange},
            ) from exc
    return pd.DataFrame(columns=EXPECTED_COLS)


def _s3_object_exists_strict(cache: str) -> bool:
    """Check S3 without confusing a missing key with an operational failure."""
    parsed = _split_s3_cache_uri(cache)
    if parsed is None:
        raise InternalServiceError("Invalid S3 cache path")
    bucket, key = parsed
    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise InternalServiceError("Failed to check S3 timeseries cache") from exc
    except BotoCoreError as exc:
        raise InternalServiceError("Failed to check S3 timeseries cache") from exc
    return True


def _create_s3_destination(destination: str, df: pd.DataFrame) -> None:
    parsed = _split_s3_cache_uri(destination)
    if parsed is None:
        raise InternalServiceError("Invalid destination cache path")
    payload = io.BytesIO()
    df.to_parquet(payload, index=False)
    bucket, key = parsed
    try:
        _s3_client().put_object(Bucket=bucket, Key=key, Body=payload.getvalue(), IfNoneMatch="*")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"PreconditionFailed", "ConditionalRequestConflict"} or status in {409, 412}:
            raise HTTPException(status_code=409, detail="Destination time series already exists") from exc
        raise InternalServiceError("Failed to create destination time series") from exc
    except BotoCoreError as exc:
        raise InternalServiceError("Failed to create destination time series") from exc
    invalidate_s3_cache_metadata(destination)


def _delete_s3_object(cache: str) -> None:
    parsed = _split_s3_cache_uri(cache)
    if parsed is None:
        raise InternalServiceError("Invalid S3 cache path")
    bucket, key = parsed
    _s3_client().delete_object(Bucket=bucket, Key=key)
    invalidate_s3_cache_metadata(cache)


def _move_timeseries(ticker: str, source_exchange: str, destination_exchange: str) -> int:
    source = meta_timeseries_cache_path(ticker, source_exchange)
    destination = meta_timeseries_cache_path(ticker, destination_exchange)
    if source == destination:
        raise HTTPException(status_code=400, detail="Source and destination must differ")

    source_exists = (
        _s3_object_exists_strict(source)
        if source.startswith("s3://")
        else has_cached_meta_timeseries(ticker, source_exchange)
    )
    if not source_exists:
        raise HTTPException(status_code=404, detail="Source time series does not exist")
    if not destination.startswith("s3://") and has_cached_meta_timeseries(ticker, destination_exchange):
        raise HTTPException(status_code=409, detail="Destination time series already exists")

    df = _load_timeseries(ticker, source_exchange)
    if df.empty:
        raise HTTPException(status_code=404, detail="Source time series does not exist")

    if destination.startswith("s3://"):
        _create_s3_destination(destination, df)
        try:
            _delete_s3_object(source)
        except Exception as exc:
            try:
                _delete_s3_object(destination)
            except Exception as rollback_exc:
                raise InternalServiceError(
                    "Failed to remove the source and could not roll back the destination",
                    extra={"ticker": ticker, "source_exchange": source_exchange},
                ) from rollback_exc
            raise InternalServiceError(
                "Failed to remove the source series; destination was rolled back",
                extra={"ticker": ticker, "source_exchange": source_exchange},
            ) from exc
    else:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Destination time series already exists") from exc
        try:
            os.unlink(source)
        except OSError:
            os.unlink(destination)
            raise
    return len(df)


@router.get("/edit")
async def get_timeseries_edit(ticker: str = Query(...), exchange: str | None = Query(None)) -> JSONResponse:
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
            df = pd.read_csv(io.StringIO(body.decode(encoding="utf-8", errors="replace")))
        else:
            payload = await request.json()
            if isinstance(payload, list):
                df = pd.DataFrame(payload)
            else:
                raise ValueError("JSON payload must be a list of records")
    except Exception as exc:
        raise ValidationFailure(
            str(exc),
            extra={"ticker": ticker, "exchange": exchange, "content_type": content_type},
        ) from exc

    df = _ensure_schema(df)
    for col in ("Ticker", "Source"):
        if col in df.columns:
            df[col] = df[col].replace("", pd.NA)
    if "Ticker" not in df.columns or df["Ticker"].isna().all():
        df["Ticker"] = ticker
    if "Source" not in df.columns or df["Source"].isna().all():
        df["Source"] = "Manual"

    cache = meta_timeseries_cache_path(ticker, exchange)
    if not cache.startswith("s3://"):
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    if cache.startswith("s3://"):
        invalidate_s3_cache_metadata(cache)
    return JSONResponse({"status": "ok", "rows": len(df)})


@router.post("/edit/move")
async def move_timeseries_edit(
    ticker: str = Query(...),
    source_exchange: str = Query(...),
    destination_exchange: str = Query(...),
) -> JSONResponse:
    ticker, source_exchange = _resolve_ticker_exchange(ticker, source_exchange)
    _, destination_exchange = _resolve_ticker_exchange(ticker, destination_exchange)
    rows = _move_timeseries(ticker, source_exchange, destination_exchange)
    return JSONResponse(
        {
            "status": "ok",
            "rows": rows,
            "ticker": ticker,
            "exchange": destination_exchange,
        }
    )
