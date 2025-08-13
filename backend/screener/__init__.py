from __future__ import annotations

"""Utilities for fetching basic valuation metrics from external APIs.

Results from :func:`fetch_fundamentals` are cached in memory keyed by
the requested ticker and the current date. Cached entries expire after a
configurable time-to-live (TTL) controlled by the ``fundamentals_cache_ttl_seconds``
setting in :mod:`backend.config`. The TTL is capped between one and seven days.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from pydantic import BaseModel

from backend.config import settings

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
# Cache configuration
_MIN_TTL = 24 * 60 * 60  # one day
_CACHE_TTL_SECONDS = max(
    _MIN_TTL,
    min(settings.fundamentals_cache_ttl_seconds, 7 * 24 * 60 * 60),
)
_CACHE: Dict[Tuple[str, str], Tuple[datetime, "Fundamentals"]] = {}

class Fundamentals(BaseModel):
    ticker: str
    name: Optional[str] = None
    peg_ratio: Optional[float] = None
    pe_ratio: Optional[float] = None
    de_ratio: Optional[float] = None
    fcf: Optional[float] = None


def _parse_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "None", "") else None
    except ValueError:
        return None


def _parse_str(value: Optional[str]) -> Optional[str]:
    return value if value not in (None, "None", "") else None


def fetch_fundamentals(ticker: str) -> Fundamentals:
    """Return key metrics for ``ticker`` using Alpha Vantage's ``OVERVIEW``
    endpoint, utilising a simple in-memory cache.
    """

    api_key = settings.alpha_vantage_key
    if not api_key:
        raise RuntimeError(
            "Alpha Vantage API key not configured; set alpha_vantage_key in config.yaml"
        )

    key = (ticker.upper(), date.today().isoformat())
    now = datetime.utcnow()

    if key in _CACHE:
        cached_at, cached_value = _CACHE[key]
        if now - cached_at < timedelta(seconds=_CACHE_TTL_SECONDS):
            return cached_value

    params = {"function": "OVERVIEW", "symbol": ticker, "apikey": api_key}
    resp = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    result = Fundamentals(
        ticker=ticker.upper(),
        name=_parse_str(data.get("Name")),
        peg_ratio=_parse_float(data.get("PEG")),
        pe_ratio=_parse_float(data.get("PERatio")),
        de_ratio=_parse_float(data.get("DebtToEquityTTM")),
        fcf=_parse_float(data.get("FreeCashFlowTTM")),
    )

    _CACHE[key] = (now, result)

    return result


def screen(
    tickers: List[str],
    *,
    peg_max: Optional[float] = None,
    pe_max: Optional[float] = None,
    de_max: Optional[float] = None,
    fcf_min: Optional[float] = None,
) -> List[Fundamentals]:
    """Fetch fundamentals for multiple tickers and filter based on thresholds."""

    results: List[Fundamentals] = []
    for tkr in tickers:
        try:
            f = fetch_fundamentals(tkr)
        except Exception:
            # Skip tickers that fail to fetch; continue with others
            continue

        if peg_max is not None and (f.peg_ratio is None or f.peg_ratio > peg_max):
            continue
        if pe_max is not None and (f.pe_ratio is None or f.pe_ratio > pe_max):
            continue
        if de_max is not None and (f.de_ratio is None or f.de_ratio > de_max):
            continue
        if fcf_min is not None and (f.fcf is None or f.fcf < fcf_min):
            continue

        results.append(f)

    return results
