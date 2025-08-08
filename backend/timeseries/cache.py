"""
Timeseries parquet-cache layer (local path, EFS, or S3).

Set TIMESERIES_CACHE_BASE to control where the parquet files live, e.g.

    export TIMESERIES_CACHE_BASE=data/timeseries          # local dev
    export TIMESERIES_CACHE_BASE=/mnt/efs/timeseries     # ECS / Lambda
    export TIMESERIES_CACHE_BASE=s3://allotmint-cache/ts # S3 bucket
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, date
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict

import pandas as pd

# ──────────────────────────────────────────────────────────────
# Remote fetchers
# ──────────────────────────────────────────────────────────────
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
from backend.utils.timeseries_helpers import _nearest_weekday, get_scaling_override, apply_scaling

OFFLINE_MODE = os.getenv("ALLOTMINT_OFFLINE_MODE", "false").lower() == "true"

logger = logging.getLogger("timeseries_cache")
logging.basicConfig(level=logging.INFO)

# ──────────────────────────────────────────────────────────────
# Cache base (local path, EFS, or S3)
# ──────────────────────────────────────────────────────────────
_CACHE_BASE: str = os.getenv("TIMESERIES_CACHE_BASE", "data/timeseries").rstrip("/")


def _cache_path(*parts: str) -> str:
    """Build a full path / S3 key under the configured base."""
    if _CACHE_BASE.startswith("s3://"):
        return "/".join([_CACHE_BASE, *parts])
    return str(Path(_CACHE_BASE, *parts))


def _ensure_local_dir(path: str) -> None:
    if not _CACHE_BASE.startswith("s3://"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────
# Weekend-safe window helper
# ──────────────────────────────────────────────────────────────
def _weekday_range(today: date, days: int) -> tuple[date, date]:
    today = _nearest_weekday(today, forward=False)  # Fri if Sat/Sun
    cutoff = _nearest_weekday(today - timedelta(days=days), forward=True)
    return cutoff, today

# ──────────────────────────────────────────────────────────────
# Parquet I/O helpers
# ──────────────────────────────────────────────────────────────
def _load_parquet(path: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(path)

        if "Date" not in df.columns:
            logger.warning("Missing 'Date' column in cache: %s", path)
            return pd.DataFrame()

        df["Date"] = pd.to_datetime(df["Date"])
        logger.debug("Loaded %s rows from cache: %s", len(df), path)
        return df
    except Exception as exc:
        logger.debug("Cache read miss (%s): %s", path, exc)
        return pd.DataFrame()


def _save_parquet(df: pd.DataFrame, path: str) -> None:
    _ensure_local_dir(path)
    df.to_parquet(path, index=False)
    logger.debug("Saved cache to %s (%s rows)", path, len(df))

# ──────────────────────────────────────────────────────────────
# Rolling parquet cache (disk/S3)
# ──────────────────────────────────────────────────────────────
def _rolling_cache(
    fetch_func: Callable[..., pd.DataFrame],
    cache_path: str,
    fetch_args: Dict,
    days: int,
    *,
    ticker: str,
    exchange: str,
) -> pd.DataFrame:

    logger.info("Rolling cache: %s", cache_path)
    cutoff, today = _weekday_range(datetime.today().date() - timedelta(days=1), days)
    existing = _load_parquet(cache_path)

    if OFFLINE_MODE:
        if existing.empty:
            raise ValueError(f"Offline mode: no cache available at {cache_path}")
        existing["Date"] = pd.to_datetime(existing["Date"]).dt.date
        return existing[(existing["Date"] >= cutoff) & (existing["Date"] <= today)]

    # live mode: update cache if needed
    if not existing.empty:
        existing["Date"] = pd.to_datetime(existing["Date"]).dt.date
        have_min, have_max = existing["Date"].min(), existing["Date"].max()

        if have_min <= cutoff and have_max >= today:
            return existing[existing["Date"] >= cutoff]

        if have_min <= cutoff <= have_max < today:
            fetch_args.update(start_date=have_max + timedelta(days=1),
                              end_date=today)
        elif cutoff < have_min:
            fetch_args.update(start_date=cutoff,
                              end_date=have_min - timedelta(days=1))
    else:
        fetch_args.update(start_date=cutoff, end_date=today)

    new = fetch_func(**fetch_args)
    if new.empty:
        logger.warning("No new timeseries data for %s.%s", ticker, exchange)
        return existing[existing["Date"] >= cutoff] if not existing.empty else pd.DataFrame()

    if "Date" not in new.columns:
        logger.warning("No Date column in new timeseries for %s.%s", ticker, exchange)
        return pd.DataFrame()
    new["Date"] = pd.to_datetime(new["Date"]).dt.date

    combined = (
        pd.concat([existing, new])
          .drop_duplicates(subset="Date")
          .sort_values("Date")
    )

    _save_parquet(combined, cache_path)
    return combined[combined["Date"] >= cutoff]

# ──────────────────────────────────────────────────────────────
# Public *disk* loaders (Yahoo / Stooq / FT / Meta)
# ──────────────────────────────────────────────────────────────
def load_yahoo_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cache = _cache_path("yahoo", f"{ticker}_{exchange}.parquet")
    return _rolling_cache(
        fetch_yahoo_timeseries_range,
        cache,
        {"ticker": ticker, "exchange": exchange},
        days,
        ticker=ticker,
        exchange=exchange,
    )


def load_ft_timeseries(ticker: str, _exchange: str, days: int) -> pd.DataFrame:
    safe = ticker.replace(":", "_")
    cache = _cache_path("ft", f"{safe}.parquet")
    return _rolling_cache(
        fetch_ft_timeseries,
        cache,
        {"ticker": ticker},
        days,
        ticker=ticker,
        exchange=_exchange,
    )


def load_stooq_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cache = _cache_path("stooq", f"{ticker}_{exchange}.parquet")
    return _rolling_cache(
        fetch_stooq_timeseries_range,
        cache,
        {"ticker": ticker, "exchange": exchange},
        days,
        ticker=ticker,
        exchange=exchange,
    )


def load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    cache = str(meta_timeseries_cache_path(ticker, exchange))
    return _rolling_cache(
        fetch_meta_timeseries,
        cache,
        {"ticker": ticker, "exchange": exchange},
        days,
        ticker=ticker,
        exchange=exchange,
    )

# ──────────────────────────────────────────────────────────────
# In-process LRU for *ranges* (no duplicate IO per request)
# ──────────────────────────────────────────────────────────────
@lru_cache(maxsize=512)
def _memoized_range(
    ticker: str,
    exchange: str,
    start_iso: str,
    end_iso: str,
) -> pd.DataFrame:
    start_date = datetime.fromisoformat(start_iso).date()
    end_date = datetime.fromisoformat(end_iso).date()
    days_span = (date.today() - start_date).days + 1

    if OFFLINE_MODE:
        cache_path = str(meta_timeseries_cache_path(ticker, exchange))
        existing = _load_parquet(cache_path)
        if existing.empty:
            logger.warning(f"Offline mode: no cached data for {ticker}")
            return pd.DataFrame()
        existing["Date"] = pd.to_datetime(existing["Date"]).dt.date
        mask = (existing["Date"] >= start_date) & (existing["Date"] <= end_date)
        return existing.loc[mask].reset_index(drop=True)

    superset = load_meta_timeseries(ticker, exchange, days_span)
    mask = (pd.to_datetime(superset["Date"]).dt.date >= start_date) & \
           (pd.to_datetime(superset["Date"]).dt.date <= end_date)
    return superset.loc[mask].reset_index(drop=True)

# ──────────────────────────────────────────────────────────────
# Public helper: explicit date range
# ──────────────────────────────────────────────────────────────
def load_meta_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
) ->  pd.DataFrame:
    for offset in range(0, 5):  # try same day, 1-day back, 2-day back...
        s = start_date - timedelta(days=offset)
        e = end_date - timedelta(days=offset)
        df = _memoized_range(ticker, exchange, s.isoformat(), e.isoformat())
        if df is not None and not df.empty:
            return df
    return pd.DataFrame()


def has_cached_meta_timeseries(ticker: str, exchange: str) -> bool:
    path = meta_timeseries_cache_path(ticker, exchange)
    return path.exists() and path.stat().st_size > 0


def meta_timeseries_cache_path(ticker: str, exchange: str) -> Path:
    return Path(_cache_path("meta", f"{ticker.upper()}_{exchange.upper()}.parquet"))


def get_price_for_date(exchange, ticker, date, field="Close"):
    df = load_meta_timeseries_range(ticker=ticker, exchange=exchange,
                                    start_date=date, end_date=date)
    if df.empty:
        return None
    scale = get_scaling_override(ticker, exchange, requested_scaling=None)
    df = apply_scaling(df, scale)
    return float(df.at[df.index[0], field])

