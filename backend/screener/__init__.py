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
    dividend_yield: Optional[float] = None
    dividend_payout_ratio: Optional[float] = None
    beta: Optional[float] = None
    shares_outstanding: Optional[int] = None
    float_shares: Optional[int] = None
    market_cap: Optional[int] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    avg_volume: Optional[int] = None


def _parse_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "None", "") else None
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value not in (None, "None", "") else None
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
        dividend_yield=_parse_float(data.get("DividendYield")),
        dividend_payout_ratio=_parse_float(data.get("PayoutRatio")),
        beta=_parse_float(data.get("Beta")),
        shares_outstanding=_parse_int(data.get("SharesOutstanding")),
        float_shares=_parse_int(data.get("SharesFloat")),
        market_cap=_parse_int(data.get("MarketCapitalization")),
        high_52w=_parse_float(data.get("52WeekHigh")),
        low_52w=_parse_float(data.get("52WeekLow")),
        avg_volume=_parse_int(data.get("AverageDailyVolume10Day")),
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
    dividend_yield_min: Optional[float] = None,
    dividend_payout_ratio_max: Optional[float] = None,
    beta_max: Optional[float] = None,
    shares_outstanding_min: Optional[int] = None,
    float_shares_min: Optional[int] = None,
    market_cap_min: Optional[int] = None,
    high_52w_max: Optional[float] = None,
    low_52w_min: Optional[float] = None,
    avg_volume_min: Optional[int] = None,
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
        if dividend_yield_min is not None and (
            f.dividend_yield is None or f.dividend_yield < dividend_yield_min
        ):
            continue
        if dividend_payout_ratio_max is not None and (
            f.dividend_payout_ratio is None
            or f.dividend_payout_ratio > dividend_payout_ratio_max
        ):
            continue
        if beta_max is not None and (f.beta is None or f.beta > beta_max):
            continue
        if shares_outstanding_min is not None and (
            f.shares_outstanding is None or f.shares_outstanding < shares_outstanding_min
        ):
            continue
        if float_shares_min is not None and (
            f.float_shares is None or f.float_shares < float_shares_min
        ):
            continue
        if market_cap_min is not None and (
            f.market_cap is None or f.market_cap < market_cap_min
        ):
            continue
        if high_52w_max is not None and (f.high_52w is None or f.high_52w > high_52w_max):
            continue
        if low_52w_min is not None and (f.low_52w is None or f.low_52w < low_52w_min):
            continue
        if avg_volume_min is not None and (
            f.avg_volume is None or f.avg_volume < avg_volume_min
        ):
            continue

        results.append(f)

    return results
