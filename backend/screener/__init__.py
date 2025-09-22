from __future__ import annotations

"""Utilities for fetching basic valuation metrics from external APIs.

Results from :func:`fetch_fundamentals` are cached in memory keyed by
the requested ticker and the current date. Cached entries expire after a
configurable time-to-live (TTL) controlled by the ``fundamentals_cache_ttl_seconds``
setting in :mod:`backend.config`. The TTL is capped between one and seven days.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
import yfinance as yf
from pydantic import BaseModel

from backend import config_module

cfg = getattr(config_module, "settings", config_module.config)
config = cfg

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
# Cache configuration
_MIN_TTL = 24 * 60 * 60  # one day
ttl_cfg = cfg.fundamentals_cache_ttl_seconds or _MIN_TTL
_CACHE_TTL_SECONDS = max(
    _MIN_TTL,
    min(ttl_cfg, 7 * 24 * 60 * 60),
)
_CACHE: Dict[Tuple[str, str], Tuple[datetime, "Fundamentals"]] = {}


class Fundamentals(BaseModel):
    ticker: str
    name: Optional[str] = None
    peg_ratio: Optional[float] = None
    pe_ratio: Optional[float] = None
    de_ratio: Optional[float] = None
    lt_de_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    fcf: Optional[float] = None
    eps: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    roa: Optional[float] = None
    roe: Optional[float] = None
    roi: Optional[float] = None
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


def _fetch_fundamentals_from_yahoo(ticker: str) -> Optional[Fundamentals]:
    """Return fundamentals sourced from Yahoo Finance or ``None`` if unavailable."""

    info = yf.Ticker(ticker).info or {}

    result = Fundamentals(
        ticker=ticker.upper(),
        name=_parse_str(info.get("shortName") or info.get("longName")),
        peg_ratio=_parse_float(info.get("pegRatio")),
        pe_ratio=_parse_float(info.get("trailingPE") or info.get("forwardPE")),
        de_ratio=_parse_float(info.get("debtToEquity")),
        lt_de_ratio=_parse_float(info.get("longTermDebtToEquity")),
        interest_coverage=_parse_float(info.get("interestCoverage")),
        current_ratio=_parse_float(info.get("currentRatio")),
        quick_ratio=_parse_float(info.get("quickRatio")),
        fcf=_parse_float(info.get("freeCashflow")),
        eps=_parse_float(info.get("trailingEps") or info.get("forwardEps")),
        gross_margin=_parse_float(info.get("grossMargins")),
        operating_margin=_parse_float(info.get("operatingMargins")),
        net_margin=_parse_float(info.get("profitMargins")),
        ebitda_margin=_parse_float(info.get("ebitdaMargins")),
        roa=_parse_float(info.get("returnOnAssets")),
        roe=_parse_float(info.get("returnOnEquity")),
        roi=_parse_float(info.get("returnOnInvestment")),
        dividend_yield=_parse_float(info.get("dividendYield")),
        dividend_payout_ratio=_parse_float(info.get("payoutRatio")),
        beta=_parse_float(info.get("beta")),
        shares_outstanding=_parse_int(info.get("sharesOutstanding")),
        float_shares=_parse_int(info.get("floatShares")),
        market_cap=_parse_int(info.get("marketCap")),
        high_52w=_parse_float(info.get("fiftyTwoWeekHigh")),
        low_52w=_parse_float(info.get("fiftyTwoWeekLow")),
        avg_volume=_parse_int(info.get("averageDailyVolume10Day") or info.get("averageVolume")),
    )

    available = result.model_dump(exclude_none=True)
    if not any(key not in {"ticker", "name"} for key in available):
        return None

    return result


def _fetch_fundamentals_from_alpha_vantage(ticker: str, api_key: str) -> Fundamentals:
    params = {"function": "OVERVIEW", "symbol": ticker, "apikey": api_key}
    resp = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    return Fundamentals(
        ticker=ticker.upper(),
        name=_parse_str(data.get("Name")),
        peg_ratio=_parse_float(data.get("PEG")),
        pe_ratio=_parse_float(data.get("PERatio")),
        de_ratio=_parse_float(data.get("DebtToEquityTTM")),
        lt_de_ratio=_parse_float(data.get("LongTermDebtToEquity")),
        interest_coverage=_parse_float(data.get("InterestCoverage")),
        current_ratio=_parse_float(data.get("CurrentRatio")),
        quick_ratio=_parse_float(data.get("QuickRatio")),
        fcf=_parse_float(data.get("FreeCashFlowTTM")),
        eps=_parse_float(data.get("EPS")),
        gross_margin=_parse_float(data.get("GrossProfitTTM")),
        operating_margin=_parse_float(data.get("OperatingMarginTTM")),
        net_margin=_parse_float(data.get("NetProfitMarginTTM")),
        ebitda_margin=_parse_float(data.get("EbitdaMarginTTM") or data.get("EBITDAMarginTTM")),
        roa=_parse_float(data.get("ReturnOnAssetsTTM")),
        roe=_parse_float(data.get("ReturnOnEquityTTM")),
        roi=_parse_float(data.get("ReturnOnInvestmentTTM")),
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


def fetch_fundamentals(ticker: str) -> Fundamentals:
    """Return key metrics for ``ticker`` using Yahoo Finance with Alpha Vantage
    fallback, utilising a simple in-memory cache."""

    api_key = cfg.alpha_vantage_key or "demo"

    key = (ticker.upper(), date.today().isoformat())
    now = datetime.now(UTC)

    if key in _CACHE:
        cached_at, cached_value = _CACHE[key]
        if now - cached_at < timedelta(seconds=_CACHE_TTL_SECONDS):
            return cached_value

    yahoo_result = None
    if not cfg.offline_mode:
        try:
            yahoo_result = _fetch_fundamentals_from_yahoo(ticker)
        except Exception:
            yahoo_result = None

    if yahoo_result is not None:
        _CACHE[key] = (datetime.now(UTC), yahoo_result)
        return yahoo_result

    result = _fetch_fundamentals_from_alpha_vantage(ticker, api_key)
    _CACHE[key] = (datetime.now(UTC), result)

    return result


def screen(
    tickers: List[str],
    *,
    peg_max: Optional[float] = None,
    pe_max: Optional[float] = None,
    de_max: Optional[float] = None,
    lt_de_max: Optional[float] = None,
    interest_coverage_min: Optional[float] = None,
    current_ratio_min: Optional[float] = None,
    quick_ratio_min: Optional[float] = None,
    fcf_min: Optional[float] = None,
    eps_min: Optional[float] = None,
    gross_margin_min: Optional[float] = None,
    operating_margin_min: Optional[float] = None,
    net_margin_min: Optional[float] = None,
    ebitda_margin_min: Optional[float] = None,
    roa_min: Optional[float] = None,
    roe_min: Optional[float] = None,
    roi_min: Optional[float] = None,
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
        if lt_de_max is not None and (f.lt_de_ratio is None or f.lt_de_ratio > lt_de_max):
            continue
        if interest_coverage_min is not None and (
            f.interest_coverage is None or f.interest_coverage < interest_coverage_min
        ):
            continue
        if current_ratio_min is not None and (f.current_ratio is None or f.current_ratio < current_ratio_min):
            continue
        if quick_ratio_min is not None and (f.quick_ratio is None or f.quick_ratio < quick_ratio_min):
            continue
        if fcf_min is not None and (f.fcf is None or f.fcf < fcf_min):
            continue
        if eps_min is not None and (f.eps is None or f.eps < eps_min):
            continue
        if gross_margin_min is not None and (f.gross_margin is None or f.gross_margin < gross_margin_min):
            continue
        if operating_margin_min is not None and (
            f.operating_margin is None or f.operating_margin < operating_margin_min
        ):
            continue
        if net_margin_min is not None and (f.net_margin is None or f.net_margin < net_margin_min):
            continue
        if ebitda_margin_min is not None and (f.ebitda_margin is None or f.ebitda_margin < ebitda_margin_min):
            continue
        if roa_min is not None and (f.roa is None or f.roa < roa_min):
            continue
        if roe_min is not None and (f.roe is None or f.roe < roe_min):
            continue
        if roi_min is not None and (f.roi is None or f.roi < roi_min):
            continue
        if dividend_yield_min is not None and (f.dividend_yield is None or f.dividend_yield < dividend_yield_min):
            continue
        if dividend_payout_ratio_max is not None and (
            f.dividend_payout_ratio is None or f.dividend_payout_ratio > dividend_payout_ratio_max
        ):
            continue
        if beta_max is not None and (f.beta is None or f.beta > beta_max):
            continue
        if shares_outstanding_min is not None and (
            f.shares_outstanding is None or f.shares_outstanding < shares_outstanding_min
        ):
            continue
        if float_shares_min is not None and (f.float_shares is None or f.float_shares < float_shares_min):
            continue
        if market_cap_min is not None and (f.market_cap is None or f.market_cap < market_cap_min):
            continue
        if high_52w_max is not None and (f.high_52w is None or f.high_52w > high_52w_max):
            continue
        if low_52w_min is not None and (f.low_52w is None or f.low_52w < low_52w_min):
            continue
        if avg_volume_min is not None and (f.avg_volume is None or f.avg_volume < avg_volume_min):
            continue
        results.append(f)

    return results
