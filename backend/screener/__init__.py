from __future__ import annotations

"""Utilities for fetching basic valuation metrics from external APIs."""

import os
from typing import List, Optional

import requests
from pydantic import BaseModel

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_KEY")


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


def fetch_fundamentals(ticker: str) -> Fundamentals:
    """Return key metrics for ``ticker`` using Alpha Vantage's ``OVERVIEW`` endpoint."""

    if not ALPHA_VANTAGE_KEY:
        raise RuntimeError("Alpha Vantage API key not configured")

    params = {"function": "OVERVIEW", "symbol": ticker, "apikey": ALPHA_VANTAGE_KEY}
    resp = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    return Fundamentals(
        ticker=ticker.upper(),
        name=data.get("Name"),
        peg_ratio=_parse_float(data.get("PEG")),
        pe_ratio=_parse_float(data.get("PERatio")),
        de_ratio=_parse_float(data.get("DebtToEquityTTM")),
        fcf=_parse_float(data.get("FreeCashFlowTTM")),
    )


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
