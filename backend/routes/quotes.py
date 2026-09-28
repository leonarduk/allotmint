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

from backend.common.currency import CurrencyNormaliser
from backend.common.errors import ProviderFailure
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.utils.lazy_import import lazy_import

# yfinance is only needed when /api/quotes is called; defer loading to first call.
yf = lazy_import("yfinance")


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/quotes")
def get_quotes(symbols: str = Query("")) -> List[Dict[str, Any]]:
    """Return quote data for the provided comma-separated ``symbols``."""

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return []

    # Skip the live yfinance round-trip entirely when running offline (see
    # backend/common/accounts_store.py and backend/common/instruments.py for
    # the same offline_mode short-circuit pattern elsewhere in the codebase).
    if config.offline_mode:
        logger.info("Skipping /api/quotes live fetch: market_data.offline_mode is enabled")
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
    failures: Dict[str, str] = {}
    for sym in syms:
        ticker = tickers.get(sym)
        if ticker is None:
            continue
        try:
            # `.info` triggers its own live network fetch; a single bad/rate
            # limited symbol must not take down the whole request (#8094).
            info = getattr(ticker, "info", {})
        except Exception as exc:  # noqa: BLE001 - isolate per-symbol provider failures
            logger.warning(
                "Failed to fetch quote info for %s, skipping: %s",
                sanitise_log_value(sym),
                sanitise_log_value(exc),
            )
            failures[sym] = str(exc)
            continue
        price = info.get("regularMarketPrice")
        if price is None:
            continue

        # Yahoo's "currency" field uses the exact-case token "GBp" for
        # LSE pence quotes, which is easy to misread as GBP -- a 100x
        # magnitude error (see #7219). Route it through the repo's single
        # source of truth for pence detection so it renders as the
        # visually distinct "GBX" instead, WITHOUT scaling the price
        # itself (CurrencyNormaliser.canonical only relabels; the raw
        # `price` above is passed through untouched). Leave currency
        # unset (None) rather than defaulting to GBP when the provider
        # gave us nothing at all -- see #7232.
        raw_currency = info.get("currency")
        currency = CurrencyNormaliser.from_raw(raw_currency).canonical if raw_currency else None

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
                # own abbreviated field (frequently hard-truncated mid-word
                # at 31 chars, e.g. "iShares Core MSCI World UCITS E" or
                # "VANGUARD FUNDS PLC VANGUARD S&P") and was being sent to
                # the frontend as if it were the full name -- #7218/#7232.
                # longName is missing for some instruments (e.g. GC=F
                # futures), hence the shortName fallback.
                "name": info.get("longName") or info.get("shortName"),
                # Currency/unit the price is quoted in, straight from the
                # provider -- never inferred from the symbol. "quote_type"
                # lets the frontend mark index levels as points rather than
                # a currency (see #7232).
                "currency": currency,
                "quote_type": info.get("quoteType"),
            }
        )

    if not results and failures:
        # Every requested symbol failed its live fetch (as opposed to simply
        # having no price data) -- surface a structured 502 rather than a
        # misleadingly "successful" empty list.
        raise ProviderFailure(
            "Failed to fetch quotes",
            extra={
                "provider": "yfinance",
                "symbols": syms,
                "provider_errors": failures,
            },
        )

    return results
