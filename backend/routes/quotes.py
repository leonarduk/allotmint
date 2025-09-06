from __future__ import annotations

"""Quotes API backed by `yfinance`.

This module exposes a single endpoint that fetches the latest quotes for the
requested symbols using ``yfinance``.  It intentionally registers the imported
``yfinance`` module as ``backend.routes.quotes.yf`` in ``sys.modules`` so that
tests can monkeypatch ``yf.Tickers`` using a dotted import path.
"""

import sys
from typing import Any, Dict, List

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

# Expose ``yf`` as a submodule for monkeypatching in tests
sys.modules[__name__ + ".yf"] = yf


router = APIRouter(prefix="/api")


@router.get("/quotes")
async def get_quotes(symbols: str = Query("")) -> List[Dict[str, Any]]:
    """Return quote data for the provided comma-separated ``symbols``."""

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return []

    try:
        tickers = yf.Tickers(" ".join(syms)).tickers
    except Exception as exc:  # pragma: no cover - exercised in tests
        raise HTTPException(status_code=502, detail=f"Failed to fetch quotes: {exc}") from exc

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
            }
        )

    return results
