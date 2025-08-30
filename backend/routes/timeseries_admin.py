from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter

from backend.common.instruments import get_instrument_meta
from backend.timeseries.cache import (
    _ensure_schema,
    load_meta_timeseries,
    meta_timeseries_cache_path,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])


@router.get("/admin")
async def timeseries_admin() -> list[dict[str, Any]]:
    base = Path("data/timeseries/meta")
    summaries: list[dict[str, Any]] = []
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
        df = df.sort_values("Date")
        earliest = df["Date"].min()
        latest = df["Date"].max()
        bdays = len(pd.bdate_range(earliest, latest)) or 1
        completeness = len(df) / bdays * 100
        latest_source = df.iloc[-1]["Source"] if "Source" in df.columns else None
        main_source = (
            df["Source"].value_counts().idxmax() if "Source" in df.columns and not df["Source"].dropna().empty else None
        )
        meta = get_instrument_meta(f"{ticker}.{exchange}")
        summaries.append(
            {
                "ticker": ticker,
                "exchange": exchange,
                "name": meta.get("name"),
                "earliest": pd.to_datetime(earliest).date().isoformat(),
                "latest": pd.to_datetime(latest).date().isoformat(),
                "completeness": round(completeness, 2),
                "latest_source": latest_source,
                "main_source": main_source,
            }
        )
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
