"""Quote snapshot endpoint using Yahoo Finance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, Query
import yfinance as yf

router = APIRouter(prefix="/api")


def _fetch(symbols: List[str]) -> List[Dict[str, Any]]:
    tickers = yf.Tickers(" ".join(symbols))
    results: List[Dict[str, Any]] = []
    for sym in symbols:
        t = tickers.tickers.get(sym)
        if not t:
            continue
        try:
            fast = t.fast_info
        except Exception:
            fast = {}
        name = None
        try:
            info = t.info
            name = info.get("shortName") or info.get("longName")
        except Exception:
            name = None
        last = fast.get("lastPrice") or fast.get("last_price")
        open_ = fast.get("open")
        high = fast.get("dayHigh") or fast.get("day_high")
        low = fast.get("dayLow") or fast.get("day_low")
        prev_close = fast.get("previousClose") or fast.get("regularMarketPreviousClose")
        change = (last - prev_close) if (last is not None and prev_close is not None) else None
        change_pct = (
            (change / prev_close * 100) if (change is not None and prev_close not in (0, None)) else None
        )
        volume = fast.get("lastVolume") or fast.get("regularMarketVolume")
        ts = fast.get("regularMarketTime")
        if ts:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            ts_iso = dt.isoformat().replace("+00:00", "Z")
        else:
            ts_iso = None
        results.append(
            {
                "name": name,
                "symbol": sym,
                "last": float(last) if last is not None else None,
                "open": float(open_) if open_ is not None else None,
                "high": float(high) if high is not None else None,
                "low": float(low) if low is not None else None,
                "change": float(change) if change is not None else None,
                "changePct": float(change_pct) if change_pct is not None else None,
                "volume": int(volume) if volume is not None else None,
                "time": ts_iso,
            }
        )
    return results


@router.get("/quotes")
async def get_quotes(symbols: str = Query("")) -> List[Dict[str, Any]]:
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        return []
    return await asyncio.to_thread(_fetch, syms)
