from __future__ import annotations

import io
import logging
import os
import re
import shutil
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
    _s3_object_recently_confirmed_missing,
    _split_s3_cache_uri,
    has_cached_meta_timeseries,
    invalidate_s3_cache_metadata,
    meta_timeseries_cache_path,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,49}$")
_EXCHANGE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,49}$")

# Actionable 404 detail for an empty/missing source: there is no cached
# series to relocate, and the real fix is correcting the holding's exchange
# so the fetcher can populate the destination (issue #6723).
_MISSING_SOURCE_DETAIL = (
    "No cached data for {ticker}.{source} - nothing to move. "
    "Correct the holding to {ticker}.{destination} so the fetcher can populate the series."
)


def _validate_cache_identifier(value: str, *, kind: str) -> str:
    """Validate an identifier before incorporating it into a cache path."""
    pattern = _TICKER_RE if kind == "ticker" else _EXCHANGE_RE
    if not pattern.fullmatch(value):
        raise ValidationFailure(f"Invalid {kind} format", extra={"field": kind})
    return value


def _resolve_ticker_exchange(ticker: str, exchange: str | None) -> tuple[str, str]:
    t = (ticker or "").upper()
    if not t:
        raise ValidationFailure("Ticker is required", extra={"field": "ticker"})

    if exchange:
        sym = _validate_cache_identifier(t.split(".", 1)[0], kind="ticker")
        ex = _validate_cache_identifier(exchange.upper(), kind="exchange")
        logger.debug("Resolved %s.%s (provided exchange)", sanitise_log_value(sym), sanitise_log_value(ex))
        return sym, ex

    if "." in t:
        sym, ex = t.split(".", 1)
        sym = _validate_cache_identifier(sym, kind="ticker")
        ex = _validate_cache_identifier(ex, kind="exchange")
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
    sym = _validate_cache_identifier(sym.upper(), kind="ticker")
    ex = _validate_cache_identifier(ex.upper(), kind="exchange")
    logger.debug("Resolved %s.%s (inferred exchange)", sanitise_log_value(sym), sanitise_log_value(ex))
    return sym, ex


def _load_timeseries(ticker: str, exchange: str) -> pd.DataFrame:
    cache = meta_timeseries_cache_path(ticker, exchange)
    exists = _s3_object_exists(cache, ticker, exchange) if cache.startswith("s3://") else Path(cache).exists()
    if exists:
        try:
            return _ensure_schema(pd.read_parquet(cache))
        except Exception as exc:  # pragma: no cover - defensive
            raise InternalServiceError(
                f"Failed to load cached timeseries for {ticker}.{exchange}",
                extra={"ticker": ticker, "exchange": exchange},
            ) from exc
    return pd.DataFrame(columns=EXPECTED_COLS)


def _s3_object_exists(cache: str, ticker: str, exchange: str) -> bool:
    parsed = _split_s3_cache_uri(cache)
    if parsed is None:
        raise InternalServiceError("Invalid S3 timeseries cache path")
    bucket, key = parsed

    if _s3_object_recently_confirmed_missing(cache):
        return False

    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        if error_code == "NoSuchBucket":
            raise InternalServiceError(
                f"S3 bucket not found for {ticker}.{exchange}; check infrastructure configuration",
                extra={"ticker": ticker, "exchange": exchange},
            )
        raise InternalServiceError(
            f"Failed to inspect cached timeseries for {ticker}.{exchange}",
            extra={"ticker": ticker, "exchange": exchange},
        ) from exc
    except BotoCoreError as exc:
        raise InternalServiceError(
            f"Failed to inspect cached timeseries for {ticker}.{exchange}",
            extra={"ticker": ticker, "exchange": exchange},
        ) from exc
    return True


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    df.to_parquet(output, index=False)
    return output.getvalue()


def _create_s3_destination(df: pd.DataFrame, destination: str) -> tuple[str, str]:
    parsed = _split_s3_cache_uri(destination)
    if parsed is None:
        raise InternalServiceError("Invalid destination cache path")
    bucket, key = parsed
    try:
        _s3_client().put_object(Bucket=bucket, Key=key, Body=_parquet_bytes(df), IfNoneMatch="*")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"412", "PreconditionFailed", "ConditionalRequestConflict"}:
            raise HTTPException(status_code=409, detail="Destination time series already exists") from exc
        raise InternalServiceError("Failed to create destination time series") from exc
    invalidate_s3_cache_metadata(destination)
    return bucket, key


def _move_s3_timeseries(df: pd.DataFrame, source: str, destination: str) -> None:
    destination_bucket, destination_key = _create_s3_destination(df, destination)
    parsed_source = _split_s3_cache_uri(source)
    if parsed_source is None:  # pragma: no cover - guarded by cache path builder
        raise InternalServiceError("Invalid source cache path")
    source_bucket, source_key = parsed_source
    try:
        _s3_client().delete_object(Bucket=source_bucket, Key=source_key)
    except Exception as exc:
        try:
            _s3_client().delete_object(Bucket=destination_bucket, Key=destination_key)
        except Exception as rollback_exc:
            raise InternalServiceError(
                "Failed to remove source and roll back destination time series"
            ) from rollback_exc
        invalidate_s3_cache_metadata(destination)
        raise InternalServiceError("Failed to remove source time series; destination was rolled back") from exc
    invalidate_s3_cache_metadata(source)


def _move_local_timeseries(source: str, destination: str) -> None:
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Atomic no-clobber via hard link: fails with FileExistsError
        # if the destination already exists, eliminating the TOCTOU
        # race that os.rename has on POSIX (silent overwrite).
        os.link(source, destination)
    except FileExistsError:
        raise HTTPException(status_code=409, detail="Destination time series already exists")
    except OSError:
        # Cross-filesystem: copy to a staging file in the destination
        # directory, then atomically link within the same filesystem.
        staging = destination_path.with_name("." + destination_path.name + ".tmp")
        shutil.copy2(source, staging)
        try:
            try:
                os.link(staging, destination)
            except FileExistsError:
                raise HTTPException(status_code=409, detail="Destination time series already exists")
        finally:
            staging.unlink(missing_ok=True)
    # Destination confirmed; remove the source.
    Path(source).unlink()


def _move_timeseries(ticker: str, source_exchange: str, destination_exchange: str) -> int:
    source = meta_timeseries_cache_path(ticker, source_exchange)
    destination = meta_timeseries_cache_path(ticker, destination_exchange)
    if source == destination:
        raise HTTPException(status_code=400, detail="Source and destination must differ")

    if not source.startswith("s3://") and not has_cached_meta_timeseries(ticker, source_exchange):
        raise HTTPException(
            status_code=404,
            detail=_MISSING_SOURCE_DETAIL.format(
                ticker=ticker, source=source_exchange, destination=destination_exchange
            ),
        )
    if not destination.startswith("s3://") and has_cached_meta_timeseries(ticker, destination_exchange):
        raise HTTPException(status_code=409, detail="Destination time series already exists")

    df = _load_timeseries(ticker, source_exchange)
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=_MISSING_SOURCE_DETAIL.format(
                ticker=ticker, source=source_exchange, destination=destination_exchange
            ),
        )

    if destination.startswith("s3://"):
        _move_s3_timeseries(df, source, destination)
    else:
        _move_local_timeseries(source, destination)
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
    requested_ticker = ticker
    ticker, source_exchange = _resolve_ticker_exchange(requested_ticker, source_exchange)
    destination_ticker, destination_exchange = _resolve_ticker_exchange(requested_ticker, destination_exchange)
    if destination_ticker != ticker:
        raise ValidationFailure("Source and destination resolve to different tickers")
    rows = _move_timeseries(ticker, source_exchange, destination_exchange)
    return JSONResponse(
        {
            "status": "ok",
            "rows": rows,
            "ticker": ticker,
            "exchange": destination_exchange,
        }
    )
