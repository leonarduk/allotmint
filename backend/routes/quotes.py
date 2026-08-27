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
logger = logging.getLogger(__name__)


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
                # longName preferred over shortName: shortName is yfinance's
                # own abbreviated field (frequently truncated mid-word, e.g.
                # "iShares Core MSCI World UCITS E") and was being sent to
                # the frontend as if it were the full name -- #7218.
                "name": info.get("longName") or info.get("shortName"),
                # Currency/unit the price is quoted in, straight from the
                # provider -- never inferred from the symbol. "quote_type"
                # lets the frontend mark index levels as points rather than
                # a currency (see #7232).
                "currency": info.get("currency"),
                "quote_type": info.get("quoteType"),
            }
        )

    return results
