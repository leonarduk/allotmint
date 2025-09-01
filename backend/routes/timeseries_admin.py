from pathlib import Path
from typing import Any
import io
import os

import pandas as pd
from fastapi import APIRouter, Depends

from backend.auth import get_current_user

from backend.common.instruments import get_instrument_meta
from backend.config import config
from backend.timeseries.cache import (
    _ensure_schema,
    load_meta_timeseries,
    meta_timeseries_cache_path,
)

router = APIRouter(
    prefix="/timeseries", tags=["timeseries"], dependencies=[Depends(get_current_user)]
)


def _summarize(df: pd.DataFrame, ticker: str, exchange: str) -> dict[str, Any]:
    """Build a summary dict for a timeseries DataFrame."""
    df = df.sort_values("Date")
    earliest = df["Date"].min()
    latest = df["Date"].max()
    bdays = len(pd.bdate_range(earliest, latest)) or 1
    completeness = len(df) / bdays * 100
    latest_source = df.iloc[-1]["Source"] if "Source" in df.columns else None
    main_source = (
        df["Source"].value_counts().idxmax()
        if "Source" in df.columns and not df["Source"].dropna().empty
        else None
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
async def timeseries_admin() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    if config.app_env == "aws":
        bucket = os.getenv("DATA_BUCKET")
        if not bucket:
            return summaries
        try:
            import boto3  # type: ignore
        except Exception:  # pragma: no cover - missing dependency
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
                except Exception:  # pragma: no cover - defensive
                    continue
                if df.empty:
                    continue
                summaries.append(_summarize(df, ticker, exchange))
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
        return summaries

    base = Path("data/timeseries/meta")
    if not base.exists():
        return summaries
    for path in sorted(base.glob("*.parquet")):
        stem = path.stem
        if "_" not in stem:
            continue
        ticker, exchange = stem.rsplit("_", 1)
        try:
            df = _ensure_schema(pd.read_parquet(path))
        except Exception:  # pragma: no cover - defensive
            continue
        if df.empty:
            continue
        summaries.append(_summarize(df, ticker, exchange))
    return summaries


@router.post("/admin/{ticker}/{exchange}/refetch")
async def refetch_timeseries(ticker: str, exchange: str) -> dict[str, Any]:
    """Fetch latest timeseries data for a ticker/exchange pair."""
    df = load_meta_timeseries(ticker.upper(), exchange.upper(), days=3650)
    return {"status": "ok", "rows": len(df)}


@router.post("/admin/{ticker}/{exchange}/rebuild_cache")
async def rebuild_cache(ticker: str, exchange: str) -> dict[str, Any]:
    """Delete and rebuild the timeseries cache for a ticker/exchange pair."""
    t = ticker.upper()
    e = exchange.upper()
    path = meta_timeseries_cache_path(t, e)
    if path.exists():
        path.unlink()
    df = load_meta_timeseries(t, e, days=3650)
    return {"status": "ok", "rows": len(df)}
