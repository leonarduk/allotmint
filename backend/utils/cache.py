import logging
import os
from datetime import datetime, timedelta, date

import pandas as pd

from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.utils.timeseries_helpers import _nearest_weekday
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries

logger = logging.getLogger("timeseries_cache")
logging.basicConfig(level=logging.DEBUG)  # DEBUG for full trace


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _weekday_range(today: date, days: int) -> tuple[date, date]:
    """
    Return (cutoff, today) so that **both** endpoints land on weekdays
    while still spanning at least *days* calendar days.
      • If today is Sat/Sun → move back to previous Fri
      • If cutoff is Sat/Sun → move forward to next Mon
    """
    today  = _nearest_weekday(today, forward=False)            # Fri if Sat/Sun
    cutoff = _nearest_weekday(today - timedelta(days=days),    # initial span
                              forward=True)                    # Mon if Sat/Sun
    return cutoff, today


def _load_cached_timeseries(path: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(path)
        df["Date"] = pd.to_datetime(df["Date"])
        logger.debug(f"Loaded {len(df)} rows from cache: {path}")
        return df
    except Exception as exc:
        logger.debug(f"Failed to load cache {path}: {exc}")
        return pd.DataFrame()


def _save_cache(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    logger.debug(f"Saved cache to {path} with {len(df)} rows")


# ──────────────────────────────────────────────────────────────
# Core rolling-cache loader
# ──────────────────────────────────────────────────────────────
def _rolling_cache(
    fetch_func,
    cache_path: str,
    fetch_args: dict,
    days: int,
) -> pd.DataFrame:
    # Weekend-safe window
    cutoff, today = _weekday_range(datetime.today().date(), days)
    logger.debug(f"Rolling cache request: {cutoff} → {today}  ({days} days)")
    logger.debug(f"Cache path: {cache_path}")

    existing = _load_cached_timeseries(cache_path)
    if not existing.empty:
        existing["Date"] = pd.to_datetime(existing["Date"]).dt.date
        have_min, have_max = existing["Date"].min(), existing["Date"].max()

        # ---- CASE 1 · full coverage --------------------------------------
        if have_min <= cutoff and have_max >= today:
            logger.debug("Cache hit: full coverage")
            return existing[existing["Date"] >= cutoff]

        # ---- Determine the missing slice ---------------------------------
        if have_min <= cutoff <= have_max < today:          # need the tail
            fetch_args["start_date"] = have_max + timedelta(days=1)
            fetch_args["end_date"]   = today
        elif cutoff < have_min:                             # need the head
            fetch_args["start_date"] = cutoff
            fetch_args["end_date"]   = have_min - timedelta(days=1)
        logger.debug("Cache partial: fetching gap %s → %s",
                     fetch_args["start_date"], fetch_args["end_date"])
    else:
        # No cache at all – honour weekday boundaries
        fetch_args["start_date"] = cutoff
        fetch_args["end_date"]   = today
        logger.debug("Empty cache: fetching %s → %s",
                     fetch_args["start_date"], fetch_args["end_date"])

    # ---- Fetch the missing data -----------------------------------------
    new_data = fetch_func(**fetch_args)
    new_data["Date"] = pd.to_datetime(new_data["Date"]).dt.date

    combined = (
        pd.concat([existing, new_data])
          .drop_duplicates(subset="Date")
          .sort_values("Date")
    )

    _save_cache(combined, cache_path)
    return combined[combined["Date"] >= cutoff]


# ──────────────────────────────────────────────────────────────
# Public loaders
# ──────────────────────────────────────────────────────────────
def load_yahoo_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cutoff, today = _weekday_range(date.today(), days)
    cache_path = os.path.join("backend/timeseries/cache/yahoo",
                              f"{ticker}_{exchange}.parquet")
    logger.debug(f"Loading Yahoo {ticker}.{exchange}  {cutoff} → {today}")
    return _rolling_cache(
        fetch_yahoo_timeseries_range,
        cache_path,
        {"ticker": ticker, "exchange": exchange,
         "start_date": cutoff, "end_date": today},
        days,
    )


def load_ft_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cutoff, today = _weekday_range(date.today(), days)
    safe_ticker   = ticker.replace(":", "_")
    cache_path    = os.path.join("backend/timeseries/cache/ft",
                                 f"{safe_ticker}.parquet")
    logger.debug(f"Loading FT {ticker}  {cutoff} → {today}")
    return _rolling_cache(
        fetch_ft_timeseries,
        cache_path,
        {"ticker": ticker, "start_date": cutoff, "end_date": today},
        days,
    )


def load_stooq_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cutoff, today = _weekday_range(date.today(), days)
    cache_path    = os.path.join("backend/timeseries/cache/stooq",
                                 f"{ticker}_{exchange}.parquet")
    logger.debug(f"Loading Stooq {ticker}.{exchange}  {cutoff} → {today}")
    return _rolling_cache(
        fetch_stooq_timeseries,
        cache_path,
        {"ticker": ticker, "exchange": exchange,
         "start_date": cutoff, "end_date": today},
        days,
    )


def load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cutoff, today = _weekday_range(date.today(), days)
    cache_path    = os.path.join("backend/timeseries/cache",
                                 f"{ticker.upper()}.parquet")
    logger.debug(f"Loading META {ticker}.{exchange}  {cutoff} → {today}")
    return _rolling_cache(
        fetch_meta_timeseries,
        cache_path,
        {"ticker": ticker, "exchange": exchange,
         "start_date": cutoff, "end_date": today},
        days,
    )
