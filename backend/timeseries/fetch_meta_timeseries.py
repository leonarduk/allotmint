"""
Meta time-series fetcher that transparently tries Yahoo → Stooq → FT
and merges the first successful result.  Now includes a helper to
return snapshot data (last price, 7-day %, 30-day %).
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
# Utilities
# ──────────────────────────────────────────────────────────────
def is_isin(ticker: str) -> bool:
    base = re.split(r"[.:]", ticker)[0].upper()
    return len(base) == 12 and base.isalnum()

def guess_currency(ticker: str) -> str:
    ticker = ticker.upper()
    if ticker.endswith(".L"):
        return "GBP"
    if ticker.endswith((".AS", ".MI")):
        return "EUR"
    if ticker.endswith((".TO", ".V")):
        return "CAD"
    return "USD"

def build_ft_ticker(ticker: str) -> Optional[str]:
    """
    Convert a plain ticker or ISIN into an FT-compatible symbol like
    'IE00B4L5Y983:GBP'.
    """
    if is_isin(ticker):
        isin = re.split(r"[.:]", ticker)[0].upper()
        currency = guess_currency(ticker)
        return f"{isin}:{currency}"
    return None

def merge_sources(sources: List[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate, de-dupe, and sort multiple dataframes."""
    if not sources:
        return pd.DataFrame()
    df = pd.concat(sources, ignore_index=True)
    df = df.drop_duplicates(subset=["Date", "Close"], keep="last")
    return df.sort_values("Date")

# ──────────────────────────────────────────────────────────────
# Single-ticker fetch
# ──────────────────────────────────────────────────────────────
def fetch_meta_timeseries(
    ticker: str,
    exchange: str = "L",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """
    Try Yahoo, then Stooq, then FT.  Returns a dataframe with columns
    Date, Open, High, Low, Close, Volume, Ticker, Source.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    start_date = _nearest_weekday(start_date, forward=False)
    end_date   = _nearest_weekday(end_date,   forward=True)

    data_sources: List[pd.DataFrame] = []

    # 1 · Yahoo
    try:
        yahoo_df = fetch_yahoo_timeseries_range(ticker, exchange, start_date, end_date)
        if not yahoo_df.empty:
            data_sources.append(yahoo_df)
    except Exception as exc:
        logger.warning(f"Yahoo fetch failed for {ticker}.{exchange}: {exc}")

    # 2 · Stooq
    try:
        stooq_df = fetch_stooq_timeseries_range(ticker, exchange, start_date, end_date)
        if not stooq_df.empty:
            data_sources.append(stooq_df)
    except Exception as exc:
        logger.warning(f"Stooq fetch failed for {ticker}.{exchange}: {exc}")

    # 3 · FT fallback
    if not data_sources:
        ft_ticker = build_ft_ticker(ticker)
        if ft_ticker:
            try:
                logger.info(f"🌍 Falling back to FT for {ft_ticker}")
                ft_df = fetch_ft_timeseries(ft_ticker, (end_date - start_date).days)
                if not ft_df.empty:
                    data_sources.append(ft_df)
            except Exception as exc:
                logger.warning(f"FT fetch failed for {ft_ticker}: {exc}")

    if not data_sources:
        logger.warning(f"No data sources succeeded for {ticker}.{exchange}")

    return merge_sources(data_sources)

# ──────────────────────────────────────────────────────────────
# Batch helpers
# ──────────────────────────────────────────────────────────────
def run_all_tickers(tickers: List[str], exchange: str = "L", days: int = 365) -> List[str]:
    today   = datetime.today().date()
    cutoff  = today - timedelta(days=days)
    success = []

    for tkr in tickers:
        try:
            df = fetch_meta_timeseries(tkr, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                success.append(tkr)
        except Exception as exc:
            logger.warning(f"[WARN] Failed to load {tkr}: {exc}")
    return success

def load_timeseries_data(
    tickers: List[str],
    exchange: str = "L",
    days: int = 365,
) -> Dict[str, pd.DataFrame]:
    today   = datetime.today().date()
    cutoff  = today - timedelta(days=days)
    result: Dict[str, pd.DataFrame] = {}

    for tkr in tickers:
        try:
            df = fetch_meta_timeseries(tkr, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                result[tkr] = df
        except Exception as exc:
            logger.warning(f"Failed to load timeseries for {tkr}: {exc}")
    return result

# ──────────────────────────────────────────────────────────────
# Latest close for a list
# ──────────────────────────────────────────────────────────────
def get_latest_closing_prices(tickers: List[str]) -> Dict[str, float]:
    """Return the most recent close for each *full* ticker (e.g. 'VWRL.L')."""
    result: Dict[str, float] = {}
    today  = datetime.today().date()
    cutoff = today - timedelta(days=365)

    for full in tickers:
        # Accept ('XDEV', 'L') as well as "XDEV.L"
        if isinstance(full, tuple):
            ticker, exchange = full
            full_ticker_str = f"{ticker}.{exchange}"
        else:
            full_ticker_str = full
            ticker, exchange = (full.split(".", 1) + ["L"])[:2]

        tkr, exch = (full_ticker_str.split(".", 1) + ["L"])[:2]
        try:
            df = fetch_meta_timeseries(tkr, exch, start_date=cutoff, end_date=today)
            if df.empty:
                logger.warning(f"No price data returned for {full_ticker_str}")
                continue
            df.columns = [c.lower() for c in df.columns]
            latest = df.sort_values("date").iloc[-1]
            result[full_ticker_str] = float(latest.get("close") or latest.get("adj close") or 0.0)
        except Exception as exc:
            logger.warning(f"{full_ticker_str}: {exc}")
    return result

# ──────────────────────────────────────────────────────────────
# Snapshot with NaN-safe 7- & 30-day deltas
# ──────────────────────────────────────────────────────────────
def get_price_snapshot(
    tickers: list[str],
    days_lookback: int = 32,
    shift_7d: int = 5,
    shift_30d: int = 22,
) -> dict[str, dict[str, float | None]]:
    """
    Returns e.g.

        {
          'XDEV.L': {
            'last_price': 38.37,
            'change_7d_pct': 1.52,
            'change_30d_pct': None,      # not enough history
            'last_price_date': '2025-08-01'
          },
          …
        }
    """
    today   = datetime.today().date()
    start   = today - timedelta(days=days_lookback)
    snap: dict[str, dict[str, float | None]] = {}

    for full in tickers:
        tkr, exch = (full.split(".", 1) + ["L"])[:2]
        df = fetch_meta_timeseries(tkr, exch, start_date=start, end_date=today)
        if df.empty:
            logger.warning(f"No data for {full}")
            continue

        df.columns = [c.lower() for c in df.columns]
        df = df.sort_values("date").reset_index(drop=True)
        df["close"] = df["close"].ffill()

        latest = float(df.iloc[-1]["close"])
        seven  = df.shift(shift_7d).iloc[-1]["close"]
        month  = df.shift(shift_30d).iloc[-1]["close"]

        def pct(now: float, then: float) -> Optional[float]:
            if pd.isna(then) or then == 0:
                return None
            return round((now - then) / then * 100, 2)

        snap[full] = {
            "last_price":       round(latest, 4),
            "change_7d_pct":    pct(latest, seven),
            "change_30d_pct":   pct(latest, month),
            "last_price_date":  str(df.iloc[-1]["date"]),
        }

    return snap

# ──────────────────────────────────────────────────────────────
# CLI · quick manual test
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today   = datetime.today().date()
    cutoff  = today - timedelta(days=700)
    sample  = fetch_meta_timeseries("GRG", "L", start_date=cutoff, end_date=today)
    print(sample.head())

    tickers = ["XDEV.L", "IEFV.L", "JEGI.L"]
    print(json.dumps(get_price_snapshot(tickers), indent=2))
