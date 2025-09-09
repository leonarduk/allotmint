from __future__ import annotations

"""Market overview endpoint aggregating indexes, sectors and headlines."""

from typing import Any, Dict, List, Optional

import logging
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
    "FTSE 100": "^FTSE",
    "FTSE 250": "^FTMC",
}


def _fetch_indexes() -> Dict[str, Dict[str, Optional[float]]]:
    tickers = yf.Tickers(" ".join(INDEX_SYMBOLS.values())).tickers
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for name, sym in INDEX_SYMBOLS.items():
        info = getattr(tickers.get(sym), "info", {})
        price = info.get("regularMarketPrice")
        change = info.get("regularMarketChangePercent")
        if price is not None:
            out[name] = {
                "value": float(price),
                "change": float(change) if change is not None else None,
            }
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
    """Fetch latest headlines for all known index symbols.

    Each index symbol is queried individually; results are aggregated and
    de-duplicated by URL or headline.  If all requests fail, an error is logged
    so callers have some visibility into the failure.
    """

    logger = logging.getLogger(__name__)
    headlines: List[Dict[str, str]] = []
    seen: set[str] = set()
    success = False

    for sym in INDEX_SYMBOLS.values():
        try:
            items = _fetch_news(sym)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to fetch news for %s: %s", sym, exc)
            continue

        success = True
        for item in items:
            key = item.get("url") or item.get("headline")
            if key and key not in seen:
                seen.add(key)
                headlines.append(item)

    if not success:
        logger.error("Failed to fetch news for all index symbols")

    return headlines


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
