import io
import logging
import os
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query, Response

from backend.auth import get_current_user
from backend.common.admin_cache_state import TIMESERIES_SUMMARIES, WARMING_HEADER, is_step_warming
from backend.common.file_signature import FileSignature, file_signature
from backend.common.instruments import METADATA_BUCKET_ENV, get_instrument_meta, instrument_meta_path
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import (
    _ensure_schema,
    clear_meta_timeseries_caches,
    load_meta_timeseries,
    meta_timeseries_cache_path,
)
from backend.timeseries.ticker_validator import is_valid_ticker

router = APIRouter(prefix="/timeseries", tags=["timeseries"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

# Summary per local parquet, reused while neither the parquet nor the
# instrument's metadata file has changed (#10754): re-reading ~1,000 parquets
# on every visit made GET /timeseries/admin take ~50s. Keyed by parquet path;
# the value is ``(signature, summary)`` and a ``None`` summary marks an empty
# series.
_SummarySignature = tuple[FileSignature, FileSignature]
_SUMMARY_CACHE: dict[Path, tuple[_SummarySignature, dict[str, Any] | None]] = {}
_SUMMARY_CACHE_LOCK = threading.Lock()


def clear_summary_cache() -> None:
    """Forget every cached per-parquet summary."""
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE.clear()


def _business_days(earliest: pd.Timestamp, latest: pd.Timestamp) -> int:
    """Weekdays from ``earliest`` to ``latest`` inclusive, like ``len(pd.bdate_range(...))``.

    ``pd.bdate_range`` builds every date in Python and was most of this
    endpoint's time across ~1,000 series (#10754).
    """
    start = pd.Timestamp(earliest).date()
    end = pd.Timestamp(latest).date() + timedelta(days=1)
    return int(np.busday_count(start, end)) if end > start else 0


def _summarize(df: pd.DataFrame, ticker: str, exchange: str) -> dict[str, Any]:
    """Build a summary dict for a timeseries DataFrame."""
    df = df.sort_values("Date")
    earliest = df["Date"].min()
    latest = df["Date"].max()
    bdays = _business_days(earliest, latest) or 1
    completeness = len(df) / bdays * 100
    latest_source = df.iloc[-1]["Source"] if "Source" in df.columns else None
    main_source = (
        df["Source"].value_counts().idxmax() if "Source" in df.columns and not df["Source"].dropna().empty else None
    )
    meta = get_instrument_meta(f"{ticker}.{exchange}")
    return {
        "ticker": ticker,
        "exchange": exchange,
        "name": meta.get("name"),
        "earliest": pd.to_datetime(earliest).date().isoformat(),
        "latest": pd.to_datetime(latest).date().isoformat(),
        "completeness": round(completeness, 2),
        "latest_source": latest_source,
        "main_source": main_source,
    }


@router.get("/admin")
def get_timeseries_admin(
    response: Response,
    partial: bool = Query(False, description="While the startup warm-up runs, return only cached summaries"),
) -> list[dict[str, Any]]:
    """Every series' summary; with ``partial`` during warm-up, only the cached ones (#10754)."""
    if partial and config.app_env != "aws" and is_step_warming(TIMESERIES_SUMMARIES):
        response.headers[WARMING_HEADER] = "true"
        return local_timeseries_summaries(cached_only=True)
    return timeseries_admin()


def timeseries_admin() -> list[dict[str, Any]]:
    """Summaries of every cached series, from S3 on AWS, else the local data root."""
    if config.app_env == "aws":
        return _s3_timeseries_summaries()
    return local_timeseries_summaries()


def _s3_timeseries_summaries() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    bucket = os.getenv("DATA_BUCKET")
    if not bucket:
        logger.warning("DATA_BUCKET environment variable is required for AWS timeseries admin")
        return summaries
    try:
        import boto3  # type: ignore
        from botocore.exceptions import ClientError  # type: ignore
    except Exception:  # pragma: no cover - missing dependency
        logger.warning("boto3 is not installed; cannot fetch timeseries metadata from S3")
        return summaries
    s3 = boto3.client("s3")
    prefix = "timeseries/meta/"
    token: str | None = None
    while True:
        params = {"Bucket": bucket, "Prefix": prefix}
        if token:
            params["ContinuationToken"] = token
        resp = s3.list_objects_v2(**params)
        for item in resp.get("Contents", []):
            key = item.get("Key", "")
            if not key.endswith(".parquet"):
                continue
            stem = Path(key).stem
            if "_" not in stem:
                continue
            ticker, exchange = stem.rsplit("_", 1)
            try:
                obj = s3.get_object(Bucket=bucket, Key=key)
                body = obj.get("Body")
                if not body:
                    continue
                df = _ensure_schema(pd.read_parquet(io.BytesIO(body.read())))
            except (ClientError, ValueError) as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load %s from S3: %s", sanitise_log_value(key), sanitise_log_value(exc))
                continue
            if df.empty:
                continue
            summaries.append(_summarize(df, ticker, exchange))
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return summaries


def local_timeseries_summaries(*, cached_only: bool = False) -> list[dict[str, Any]]:
    """Summaries of every parquet under ``data_root/timeseries/meta``.

    With ``cached_only`` a parquet with no up-to-date cached summary is skipped
    instead of read, so the call costs a directory listing plus a ``stat`` per
    file; used while the startup warm-up is still filling the cache.
    """
    summaries: list[dict[str, Any]] = []
    base = config.data_root / "timeseries" / "meta"
    if not base.exists():
        return summaries
    paths = sorted(base.glob("*.parquet"))
    for path in paths:
        stem = path.stem
        if "_" not in stem:
            continue
        ticker, exchange = stem.rsplit("_", 1)
        summary = _local_summary(path, ticker, exchange, cached_only=cached_only)
        if summary is not None:
            summaries.append(summary)
    _prune_summary_cache(base, set(paths))
    return summaries


def _meta_signature(ticker: str, exchange: str) -> FileSignature:
    try:
        return file_signature(instrument_meta_path(ticker, exchange))
    except ValueError:
        return None


def _local_summary(path: Path, ticker: str, exchange: str, *, cached_only: bool = False) -> dict[str, Any] | None:
    """Summary for one local parquet, served from the cache while its files are unchanged.

    With ``cached_only``, ``None`` when there is no up-to-date cached summary.
    """
    # Same policy as the Data Quality series cache: never on AWS, and not when
    # metadata comes from S3, since either can change without a local file
    # changing.
    cacheable = config.app_env != "aws" and not os.getenv(METADATA_BUCKET_ENV)
    signature = (file_signature(path), _meta_signature(ticker, exchange))
    if cacheable:
        with _SUMMARY_CACHE_LOCK:
            cached = _SUMMARY_CACHE.get(path)
        if cached is not None and cached[0] == signature:
            return dict(cached[1]) if cached[1] is not None else None
    if cached_only:
        return None
    try:
        df = _ensure_schema(pd.read_parquet(path))
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load %s: %s", sanitise_log_value(path), sanitise_log_value(exc))
        return None
    summary = None if df.empty else _summarize(df, ticker, exchange)
    if cacheable:
        with _SUMMARY_CACHE_LOCK:
            _SUMMARY_CACHE[path] = (signature, summary)
    return dict(summary) if summary is not None else None


def _prune_summary_cache(base: Path, present: set[Path]) -> None:
    """Forget summaries for parquets under ``base`` that no longer exist (other roots are left alone)."""
    with _SUMMARY_CACHE_LOCK:
        for stale in [p for p in _SUMMARY_CACHE if p.parent == base and p not in present]:
            del _SUMMARY_CACHE[stale]


@router.post("/admin/{ticker}/{exchange}/refetch")
def refetch_timeseries(ticker: str, exchange: str) -> dict[str, Any]:
    """Fetch latest timeseries data for a ticker/exchange pair.

    Drops the in-process caches first so a ticker whose earlier lookup came
    back empty (e.g. before its metadata existed) is fetched afresh (#9963).
    """
    is_valid_ticker.cache_clear()
    clear_meta_timeseries_caches()
    df = load_meta_timeseries(ticker.upper(), exchange.upper(), days=3650)
    return {"status": "ok", "rows": len(df)}


@router.post("/admin/{ticker}/{exchange}/rebuild_cache")
def rebuild_cache(ticker: str, exchange: str) -> dict[str, Any]:
    """Delete and rebuild the timeseries cache for a ticker/exchange pair."""
    t = ticker.upper()
    e = exchange.upper()
    path = meta_timeseries_cache_path(t, e)
    if path.exists():
        path.unlink()
    df = load_meta_timeseries(t, e, days=3650)
    return {"status": "ok", "rows": len(df)}
