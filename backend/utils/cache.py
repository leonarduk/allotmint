import os
import logging
import pandas as pd
from datetime import datetime, timedelta, date

from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range

logger = logging.getLogger("timeseries_cache")
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for full trace


def _load_cached_timeseries(path: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(path)
        df["Date"] = pd.to_datetime(df["Date"])
        logger.debug(f"Loaded {len(df)} rows from cache: {path}")
        return df
    except Exception as e:
        logger.debug(f"Failed to load cache from {path}: {e}")
        return pd.DataFrame()


def _save_cache(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    logger.debug(f"Saved cache to {path} with {len(df)} rows")


def _rolling_cache(fetch_func, cache_path: str, fetch_args: dict, days: int) -> pd.DataFrame:
    today = datetime.today().date()
    cutoff = today - timedelta(days=days)

    logger.debug(f"Rolling cache requested for {days} days: cutoff={cutoff}, today={today}")
    logger.debug(f"Cache path: {cache_path}")

    existing = _load_cached_timeseries(cache_path)

    # Normalize to plain date
    if not existing.empty:
        existing["Date"] = pd.to_datetime(existing["Date"]).dt.date
        if existing["Date"].max() >= today and existing["Date"].min() <= cutoff:
            logger.debug("Cache hit: using existing data")
            return existing[existing["Date"] >= cutoff]

    logger.debug("Cache miss or incomplete: fetching fresh data using %s with args %s", fetch_func.__name__, fetch_args)
    new_data = fetch_func(**fetch_args)
    new_data["Date"] = pd.to_datetime(new_data["Date"]).dt.date

    combined = pd.concat([existing, new_data])
    combined = combined.drop_duplicates(subset="Date").sort_values("Date")
    combined["Date"] = pd.to_datetime(combined["Date"]).dt.date

    _save_cache(combined, cache_path)
    return combined[combined["Date"] >= cutoff]


def load_yahoo_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    today = date.today()
    start_date = today - timedelta(days=days)
    cache_path = os.path.join("backend/timeseries/cache/yahoo", f"{ticker}_{exchange}.parquet")

    logger.debug(f"Loading Yahoo data for {ticker} ({exchange}) over {days} days ({start_date} to {today})")

    return _rolling_cache(
        fetch_yahoo_timeseries_range,
        cache_path,
        {"ticker": ticker, "exchange": exchange, "start_date": start_date, "end_date": today},
        days
    )


def load_ft_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    safe_ticker = ticker.replace(":", "_")
    cache_path = os.path.join("backend/timeseries/cache/ft", f"{safe_ticker}.parquet")

    logger.debug(f"Loading FT data for {ticker} over {days} days")

    return _rolling_cache(
        fetch_ft_timeseries,
        cache_path,
        {"ticker": ticker},
        days
    )


def load_stooq_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cache_path = os.path.join("backend/timeseries/cache/stooq", f"{ticker}_{exchange}.parquet")

    logger.debug(f"Loading Stooq data for {ticker} ({exchange}) over {days} days")

    return _rolling_cache(
        fetch_stooq_timeseries,
        cache_path,
        {"ticker": ticker, "exchange": exchange, "days": days},  # ✅ Now explicitly pass `days`
        days
    )

from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries

def load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cache_path = os.path.join("backend/timeseries/cache", f"{ticker.upper()}.parquet")
    today = date.today()
    start_date = today - timedelta(days=days)

    return _rolling_cache(
        fetch_meta_timeseries,
        cache_path,
        {"ticker": ticker, "exchange": exchange, "start_date": start_date, "end_date": today},
        days
    )
