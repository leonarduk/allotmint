from __future__ import annotations

"""Quotes API backed by `yfinance`.

This module exposes a single endpoint that fetches the latest quotes for the
requested symbols using ``yfinance``.  ``yf`` is a lazy proxy so that the
heavy yfinance import is deferred until the endpoint is first called.  Test
monkeypatching via ``monkeypatch.setattr("backend.routes.quotes.yf.Tickers",
...)`` works transparently because the proxy delegates attribute
reads/writes to the real module once loaded.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from backend.common.errors import ProviderFailure
from backend.utils.lazy_import import lazy_import

# yfinance is only needed when /api/quotes is called; defer loading to first call.
yf = lazy_import("yfinance")


router = APIRouter(prefix="/api")
logger = logging.getLogger("routes.quotes")


@router.get("/quotes")
async def get_quotes(symbols: str = Query("")) -> List[Dict[str, Any]]:
    """Return quote data for the provided comma-separated ``symbols``."""

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return []

    try:
        tickers = yf.Tickers(" ".join(syms)).tickers
    except Exception as exc:  # pragma: no cover - exercised in tests
        raise ProviderFailure(
            "Failed to fetch quotes",
            extra={
                "provider": "yfinance",
                "symbols": syms,
                "provider_error": str(exc),
            },
        ) from exc

    results: List[Dict[str, Any]] = []
    for sym in syms:
        ticker = tickers.get(sym)
        if ticker is None:
            continue
        info = getattr(ticker, "info", {})
        price = info.get("regularMarketPrice")
        if price is None:
            continue
        results.append(
            {
                "symbol": sym,
                "price": price,
                "open": info.get("regularMarketOpen"),
                "high": info.get("regularMarketDayHigh"),
                "low": info.get("regularMarketDayLow"),
                "previous_close": info.get("regularMarketPreviousClose"),
                "volume": info.get("regularMarketVolume"),
                "timestamp": info.get("regularMarketTime"),
                "timezone": info.get("exchangeTimezoneName"),
                "market_state": info.get("marketState"),
                "name": info.get("shortName") or info.get("longName"),
            }
        )

    return results
