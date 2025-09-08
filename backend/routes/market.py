from __future__ import annotations

"""Market overview endpoint aggregating indexes, sectors and headlines."""

from typing import Any, Dict, List

import requests
import yfinance as yf
from fastapi import APIRouter

from backend.config import config
from backend.routes.news import _fetch_news

router = APIRouter(tags=["market"])

INDEX_SYMBOLS = {
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "NASDAQ": "^IXIC",
}


def _fetch_indexes() -> Dict[str, float]:
    tickers = yf.Tickers(" ".join(INDEX_SYMBOLS.values())).tickers
    out: Dict[str, float] = {}
    for name, sym in INDEX_SYMBOLS.items():
        info = getattr(tickers.get(sym), "info", {})
        price = info.get("regularMarketPrice")
        if price is not None:
            out[name] = float(price)
    return out


def _fetch_sectors() -> List[Dict[str, float]]:
    params = {"function": "SECTOR", "apikey": config.alpha_vantage_key or "demo"}
    resp = requests.get("https://www.alphavantage.co/query", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("Rank A: Real-Time Performance", {})
    out: List[Dict[str, float]] = []
    for sector, change in data.items():
        try:
            out.append({"sector": sector, "change": float(change.rstrip("%"))})
        except Exception:
            continue
    return out


def _fetch_headlines() -> List[Dict[str, str]]:
    return _fetch_news("SPY")


def _safe(func, default):
    try:
        return func()
    except Exception:  # pragma: no cover - network errors
        return default


@router.get("/market/overview")
async def market_overview() -> Dict[str, Any]:
    """Return index levels, sector performance and latest headlines."""

    indexes = _safe(_fetch_indexes, {})
    sectors = _safe(_fetch_sectors, [])
    headlines = _safe(_fetch_headlines, [])
    return {"indexes": indexes, "sectors": sectors, "headlines": headlines}
