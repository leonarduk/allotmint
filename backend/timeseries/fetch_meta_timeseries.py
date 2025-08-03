import logging
import re
from datetime import date, timedelta, datetime
from typing import List, Optional, Dict

import pandas as pd

from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.utils.timeseries_helpers import _nearest_weekday

logger = logging.getLogger("meta_timeseries")

# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────
def is_isin(ticker: str) -> bool:
    """Check if the base part of a ticker is a valid ISIN-like identifier."""
    base = re.split(r"[.:]", ticker)[0].upper()
    return len(base) == 12 and base.isalnum()

def guess_currency(ticker: str) -> str:
    ticker = ticker.upper()
    if ticker.endswith(".L"):
        return "GBP"
    if ticker.endswith(".AS") or ticker.endswith(".MI"):
        return "EUR"
    if ticker.endswith(".TO") or ticker.endswith(".V"):
        return "CAD"
    return "USD"

def build_ft_ticker(ticker: str) -> Optional[str]:
    if is_isin(ticker):
        isin = re.split(r"[.:]", ticker)[0].upper()
        currency = guess_currency(ticker)
        return f"{isin}:{currency}"
    return None

def merge_sources(sources: List[pd.DataFrame]) -> pd.DataFrame:
    if not sources:
        return pd.DataFrame()
    df = pd.concat(sources, ignore_index=True)
    df = df.drop_duplicates(subset=["Date", "Close"], keep="last")
    df = df.sort_values("Date")
    return df

# ──────────────────────────────────────────────────────────────
# Fetch single timeseries
# ──────────────────────────────────────────────────────────────
def fetch_meta_timeseries(
        ticker: str,
        exchange: str = "L",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
) -> pd.DataFrame:
    logger.info(f"📊 Fetching latest prices for: {ticker}.{exchange}")

    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    start_date = _nearest_weekday(start_date, forward=False)
    end_date = _nearest_weekday(end_date, forward=True)

    data_sources = []

    # 1. Try Yahoo
    try:
        yahoo_df = fetch_yahoo_timeseries_range(ticker, exchange, start_date, end_date)
        if not yahoo_df.empty:
            data_sources.append(yahoo_df)
    except Exception as e:
        logger.warning(f"Yahoo fetch failed for {ticker}.{exchange}: {e}")

    # 2. Try Stooq
    try:
        stooq_df = fetch_stooq_timeseries_range(ticker, exchange, start_date, end_date)
        if not stooq_df.empty:
            data_sources.append(stooq_df)
    except Exception as e:
        logger.warning(f"Stooq fetch failed for {ticker}.{exchange}: {e}")

    # 3. FT fallback if needed
    if not data_sources:
        ft_ticker = build_ft_ticker(ticker)
        if ft_ticker:
            try:
                logger.info(f"🌍 Falling back to FT for {ft_ticker}")
                ft_df = fetch_ft_timeseries(ft_ticker, (end_date - start_date).days)
                if not ft_df.empty:
                    data_sources.append(ft_df)
            except Exception as e:
                logger.warning(f"FT fetch failed for {ft_ticker}: {e}")

    if not data_sources:
        logger.warning(f"No data sources succeeded for {ticker}.{exchange}")

    return merge_sources(data_sources)

# ──────────────────────────────────────────────────────────────
# Batch fetch
# ──────────────────────────────────────────────────────────────
def run_all_tickers(tickers: List[str], exchange: str = "L", days: int = 365) -> List[str]:
    today = datetime.today().date()
    cutoff = today - timedelta(days=days)

    processed = []
    for ticker in tickers:
        try:
            df = fetch_meta_timeseries(ticker, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                processed.append(ticker)
        except Exception as e:
            logger.warning(f"[WARN] Failed to load {ticker}: {e}")
    return processed

def load_timeseries_data(tickers: List[str], exchange: str = "L", days: int = 365) -> Dict[str, pd.DataFrame]:
    today = datetime.today().date()
    cutoff = today - timedelta(days=days)
    result = {}

    for ticker in tickers:
        try:
            df = fetch_meta_timeseries(ticker, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                result[ticker] = df
        except Exception as e:
            logger.warning(f"Failed to load timeseries for {ticker}: {e}")
    return result

# ──────────────────────────────────────────────────────────────
# Closing price summary
# ──────────────────────────────────────────────────────────────
def get_latest_closing_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Accepts tickers like 'VWRL.L', 'ULVR.L', 'ALW', and returns latest close per full ticker.
    """
    result = {}
    today = datetime.today().date()
    cutoff = today - timedelta(days=365)

    for full_ticker in tickers:
        # extract ticker and exchange from full_ticker
        if "." in full_ticker:
            ticker, exchange = full_ticker.split(".", 1)
        else:
            ticker, exchange = full_ticker, "L"

        try:
            df = fetch_meta_timeseries(ticker, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df_sorted = df.sort_values("date")
                latest_row = df_sorted.iloc[-1]
                price = float(latest_row.get("close") or latest_row.get("adj close") or 0.0)
                result[f"{ticker}.{exchange}"] = price
                logger.debug(f"[{ticker}.{exchange}] latest close = {price}")
            else:
                logger.warning(f"No price data returned for {ticker}.{exchange}")
        except Exception as e:
            logger.warning(f"[{ticker}.{exchange}] Failed: {e}")
    return result

# ──────────────────────────────────────────────────────────────
# CLI for testing
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today = datetime.today().date()
    cutoff = today - timedelta(days=700)
    df = fetch_meta_timeseries("GRG", "LSE", start_date=cutoff, end_date=today)
    print(df.head())
