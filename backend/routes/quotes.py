from __future__ import annotations

"""API route to fetch live quotes from Yahoo Finance."""

from datetime import datetime, timezone
from typing import List, Optional

import yfinance as yf
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api", tags=["quotes"])


def _fmt_time(ts: Optional[int]) -> Optional[str]:
    """Convert UNIX seconds to an ISO-8601 UTC string."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@router.get("/quotes")
async def get_quotes(symbols: str = Query(..., description="Comma-separated tickers")):
    """Return snapshot quotes for the requested Yahoo Finance symbols."""
    sym_list: List[str] = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return []

    tickers = yf.Tickers(" ".join(sym_list))
    rows = []

    for sym in sym_list:
        t = tickers.tickers.get(sym)
        if t is None:
            continue

        info = t.fast_info or {}
        last = info.get("lastPrice")
        open_ = info.get("open")
        high = info.get("dayHigh")
        low = info.get("dayLow")
        prev_close = info.get("previousClose")
        volume = info.get("volume")
        ts = info.get("lastMarketTime") or info.get("regularMarketTime")

        change = change_pct = None
        if last is not None and prev_close not in (None, 0):
            change = last - prev_close
            change_pct = change / prev_close * 100

        name = info.get("longName") or info.get("shortName") or sym

        rows.append(
            {
                "name": name,
                "symbol": sym,
                "last": last,
                "open": open_,
                "high": high,
                "low": low,
                "change": change,
                "changePct": change_pct,
                "volume": volume,
                "time": _fmt_time(ts),
            }
        )

    return rows
