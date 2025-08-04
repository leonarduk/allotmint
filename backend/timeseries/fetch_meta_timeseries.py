"""
Meta time-series fetcher that transparently tries Yahoo → Stooq → FT
and merges the first successful result. Helpers return snapshots
(last price, 7-day %, 30-day %).

2025-08-04 — smarter merge:
  • Fetch Yahoo first; if coverage < 95 % of the requested window,
    supplement from Stooq, then FT.
  • Added ticker sanity-check and quieter logging for expected fall-backs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict

import pandas as pd

# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.utils.timeseries_helpers import _nearest_weekday

logger = logging.getLogger("meta_timeseries")

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
_TICKER_RE = re.compile(r"^[A-Za-z0-9]{1,12}(?:\.[A-Z]{1,3})?$")


def _is_isin(ticker: str) -> bool:
    base = re.split(r"[.:]", ticker)[0].upper()
    return len(base) == 12 and base.isalnum()


def _guess_currency(ticker: str) -> str:
    ticker = ticker.upper()
    if ticker.endswith(".L"):
        return "GBP"
    if ticker.endswith((".AS", ".MI")):
        return "EUR"
    if ticker.endswith((".TO", ".V")):
        return "CAD"
    return "USD"


def _build_ft_ticker(ticker: str) -> Optional[str]:
    """Return an FT-compatible symbol like 'IE00B4L5Y983:GBP', or None."""
    if _is_isin(ticker):
        isin = re.split(r"[.:]", ticker)[0].upper()
        return f"{isin}:{_guess_currency(ticker)}"
    return None


def _merge(sources: List[pd.DataFrame]) -> pd.DataFrame:
    if not sources:
        return pd.DataFrame()
    df = pd.concat(sources, ignore_index=True)
    df = df.drop_duplicates(subset=["Date", "Close"], keep="last")
    return df.sort_values("Date").reset_index(drop=True)


def _coverage_ratio(df: pd.DataFrame,
                    expected: set[date]) -> float:
    if df.empty or not expected:
        return 0.0
    present = set(pd.to_datetime(df["Date"]).dt.date)
    return len(present & expected) / len(expected)

# ──────────────────────────────────────────────────────────────
# Core fetch
# ──────────────────────────────────────────────────────────────
def fetch_meta_timeseries(
    ticker: str,
    exchange: str = "L",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    *,
    min_coverage: float = 0.95,          # 95 % of trading days
) -> pd.DataFrame:
    """
    Fetch price history from Yahoo, Stooq, FT — only as much as needed.

    Returns DF[Date, Open, High, Low, Close, Volume, Ticker, Source].
    """
    # ── Guard rails ────────────────────────────────────────────
    if not _TICKER_RE.match(ticker):
        logger.warning("Ticker pattern looks invalid: %s", ticker)
        return pd.DataFrame()

    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    start_date = _nearest_weekday(start_date, forward=False)
    end_date   = _nearest_weekday(end_date,   forward=True)

    # Weekday grid we want to fill
    expected_dates = set(pd.bdate_range(start_date, end_date).date)

    data: list[pd.DataFrame] = []

    # ── 1 · Yahoo ─────────────────────────────────────────────
    try:
        yahoo = fetch_yahoo_timeseries_range(ticker, exchange,
                                             start_date, end_date)
        if not yahoo.empty:
            data.append(yahoo)
            if _coverage_ratio(yahoo, expected_dates) >= min_coverage:
                return yahoo
    except Exception as exc:
        logger.info("Yahoo miss for %s.%s: %s", ticker, exchange, exc)

    # ── 2 · Stooq (fill gaps only if needed) ──────────────────
    try:
        stooq = fetch_stooq_timeseries_range(ticker, exchange,
                                             start_date, end_date)
        if not stooq.empty:
            combined = _merge([*data, stooq])
            if _coverage_ratio(combined, expected_dates) >= min_coverage:
                return combined
            data.append(stooq)
    except Exception as exc:
        logger.info("Stooq miss for %s.%s: %s", ticker, exchange, exc)

    # ── 3 · FT fallback – last resort ─────────────────────────
    ft_ticker = _build_ft_ticker(ticker)
    if ft_ticker:
        try:
            logger.info("🌍 Falling back to FT for %s", ft_ticker)
            days = (end_date - start_date).days or 1
            ft_df = fetch_ft_timeseries(ft_ticker, days)
            if not ft_df.empty:
                data.append(ft_df)
        except Exception as exc:
            logger.info("FT miss for %s: %s", ft_ticker, exc)

    if not data:
        logger.warning("No data sources succeeded for %s.%s",
                       ticker, exchange)
        return pd.DataFrame()

    return _merge(data)

# ──────────────────────────────────────────────────────────────
# Cache-aware batch helpers (local import) ─────────────────────
def run_all_tickers(tickers: List[str],
                    exchange: str = "L",
                    days: int = 365) -> List[str]:
    """Warm-up helper – returns tickers that produced data."""
    from backend.timeseries.cache import load_meta_timeseries
    ok: list[str] = []
    for t in tickers:
        try:
            if not load_meta_timeseries(t, exchange, days).empty:
                ok.append(t)
        except Exception as exc:
            logger.warning("[WARN] %s: %s", t, exc)
    return ok


def load_timeseries_data(
    tickers: List[str], exchange: str = "L", days: int = 365
) -> Dict[str, pd.DataFrame]:
    """Return {ticker: dataframe} using the parquet cache."""
    from backend.timeseries.cache import load_meta_timeseries
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = load_meta_timeseries(t, exchange, days)
            if not df.empty:
                out[t] = df
        except Exception as exc:
            logger.warning("Load fail %s: %s", t, exc)
    return out

# ─────────────────────────────────────────────────────────
