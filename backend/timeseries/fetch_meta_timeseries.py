"""
Meta time-series fetcher that transparently tries Yahoo -> Stooq -> Alpha Vantage -> FT
and merges the first successful result. Helpers return snapshots
(last price, 7-day %, 30-day %).

2025-08-04 - smarter merge:
  - Fetch Yahoo first; if coverage < 95 % of the requested window,
    supplement from Stooq, Alpha Vantage, then FT.
  - Added ticker sanity-check and quieter logging for expected fall-backs.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta, datetime
from typing import List, Optional, Dict

import pandas as pd

# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.timeseries.fetch_alphavantage_timeseries import (
    fetch_alphavantage_timeseries_range,
)
from backend.utils.timeseries_helpers import _nearest_weekday, _is_isin, STANDARD_COLUMNS

logger = logging.getLogger("meta_timeseries")

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
_TICKER_RE = re.compile(r"^[A-Za-z0-9]{1,12}(?:[-\.][A-Z]{1,3})?$")



def _merge(sources: List[pd.DataFrame]) -> pd.DataFrame:
    if not sources:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
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
    Fetch price history from Yahoo, Stooq, FT - only as much as needed.

    Returns DF[Date, Open, High, Low, Close, Volume, Ticker, Source].
    """
    # ── Guard rails ────────────────────────────────────────────
    if not ticker or not ticker.strip():
        logger.warning("Ticker pattern looks invalid: empty or whitespace")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    if not _TICKER_RE.match(ticker):
        logger.warning("Ticker pattern looks invalid: %s", ticker)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    if end_date is None:
        end_date = date.today() - timedelta(days=1)
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    start_date = _nearest_weekday(start_date, forward=False)
    end_date   = _nearest_weekday(end_date,   forward=True)

    # Weekday grid we want to fill
    expected_dates = set(pd.bdate_range(start_date, end_date).date)

    data: list[pd.DataFrame] = []

    if _is_isin(ticker=ticker):
        ft_df = fetch_ft_df(ticker, end_date, start_date)

        if not ft_df.empty:
            return ft_df

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

    # ── 3 · Alpha Vantage (fill gaps if still needed) ─────────
    try:
        av = fetch_alphavantage_timeseries_range(
            ticker, exchange, start_date, end_date
        )
        if not av.empty:
            combined = _merge([*data, av])
            if _coverage_ratio(combined, expected_dates) >= min_coverage:
                return combined
            data.append(av)
    except Exception as exc:
        logger.info("Alpha Vantage miss for %s.%s: %s", ticker, exchange, exc)

    # ── 4 · FT fallback – last resort ─────────────────────────
    ft_df = fetch_ft_df(ticker, end_date, start_date)

    if not ft_df.empty:
        data.append(ft_df)

    if not data:
        logger.warning("No data sources succeeded for %s.%s",
                       ticker, exchange)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = _merge(data)
    # Ensure we compare like-for-like datatypes. Some sources (e.g. FT) may
    # return plain ``datetime.date`` objects which cannot be directly
    # compared against ``pd.Timestamp``. Convert the column on the fly to
    # Timestamp before applying the end-date filter.
    df = df[pd.to_datetime(df["Date"]) <= pd.to_datetime(end_date)]
    return df


def fetch_ft_df(ticker, end_date, start_date):
    try:
        logger.info(f"Falling back to FT for {ticker}")
        days = (end_date - start_date).days or 1
        ft_df = fetch_ft_timeseries(ticker, days)
        return ft_df
    except Exception as exc:
        logger.info("FT miss for %s: %s", ticker, exc)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

# ──────────────────────────────────────────────────────────────
# Cache-aware batch helpers (local import) ─────────────────────
def run_all_tickers(tickers: List[str],
                    exchange: str = "L",
                    days: int = 365) -> List[str]:
    """Warm-up helper - returns tickers that produced data."""
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

if __name__ == "__main__":
    # Example usage
    today = datetime.today().date()
    cutoff = today - timedelta(days=700)

    df = fetch_meta_timeseries("1", "", start_date=cutoff, end_date=today)
    print("Returned: %s", df.head())

