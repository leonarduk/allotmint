"""
Timeseries parquet-cache layer (local path, EFS, or S3).

Set TIMESERIES_CACHE_BASE to control where the parquet files live, e.g.

    export TIMESERIES_CACHE_BASE=data/timeseries          # local dev
    export TIMESERIES_CACHE_BASE=/mnt/efs/timeseries     # ECS / Lambda
    export TIMESERIES_CACHE_BASE=s3://allotmint-cache/ts # S3 bucket
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict

import pandas as pd
import requests

from backend.common.instruments import get_instrument_meta
from backend.config import config

# ──────────────────────────────────────────────────────────────
# Remote fetchers
# ──────────────────────────────────────────────────────────────
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.utils.fx_rates import fetch_fx_rate_range
from backend.utils.timeseries_helpers import _nearest_weekday, apply_scaling, get_scaling_override

OFFLINE_MODE = config.offline_mode

logger = logging.getLogger("timeseries_cache")

# Expected schema for any timeseries DF we return
EXPECTED_COLS = ["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]

EXCHANGE_TO_CCY = {
    "L": "GBP",
    "LSE": "GBP",
    "UK": "GBP",
    "N": "USD",
    "US": "USD",
    "NASDAQ": "USD",
    "NYSE": "USD",
    "DE": "EUR",
    "F": "EUR",
    "PARIS": "EUR",
    "XETRA": "EUR",
    "SW": "CHF",
    "JP": "JPY",
    "CA": "CAD",
    "TO": "CAD",
}


def _empty_ts() -> pd.DataFrame:
    """Guaranteed-schema empty frame."""
    return pd.DataFrame(columns=EXPECTED_COLS)


def _ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Make sure DF has the expected columns; if not, return an empty DF with schema.
    Also normalizes 'Date' to datetime64[ns] (not date) here.
    """
    if df is None or df.empty:
        return _empty_ts()
    # If no Date col -> bail to empty with schema
    if "Date" not in df.columns:
        logger.warning("Timeseries missing 'Date' column; returning empty with schema")
        return _empty_ts()
    # Reindex columns (keep extras too, but ensure expected exist)
    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    # Return only expected columns in expected order (stable)
    return df[EXPECTED_COLS]


# ──────────────────────────────────────────────────────────────
# Cache base (local path, EFS, or S3)
# ──────────────────────────────────────────────────────────────
_CACHE_BASE: str = config.timeseries_cache_base


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
        df = _ensure_schema(df)
        logger.debug("Loaded %s rows from cache: %s", len(df), path)
        return df
    except Exception as exc:
        logger.debug("Cache read miss (%s): %s", path, exc)
        return _empty_ts()


def _save_parquet(df: pd.DataFrame, path: str) -> None:
    df = _ensure_schema(df)
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

    logger.debug("Rolling cache: %s", cache_path)
    # Only look up to yesterday (we have close prices only)
    cutoff, today = _weekday_range(datetime.today().date() - timedelta(days=1), days)

    existing = _load_parquet(cache_path)

    if OFFLINE_MODE:
        if existing.empty:
            raise ValueError(f"Offline mode: no cache available at {cache_path}")
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        mask = (ex["Date"] >= cutoff) & (ex["Date"] <= today)
        return _ensure_schema(ex.loc[mask].reset_index(drop=True))

    # live mode: update cache if needed
    if not existing.empty:
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        have_min, have_max = ex["Date"].min(), ex["Date"].max()

        # Already fully covered
        if have_min <= cutoff and have_max >= today:
            return _ensure_schema(existing[existing["Date"].dt.date >= cutoff].reset_index(drop=True))

        # Need to extend forward only
        if have_min <= cutoff <= have_max < today:
            fetch_args.update(start_date=have_max + timedelta(days=1), end_date=today)
        # Need to fetch earlier window chunk
        elif cutoff < have_min:
            fetch_args.update(start_date=cutoff, end_date=have_min - timedelta(days=1))
    else:
        fetch_args.update(start_date=cutoff, end_date=today)

    new = fetch_func(**fetch_args)
    new = _ensure_schema(new)

    if new.empty:
        logger.warning("No new timeseries data for %s.%s", ticker, exchange)
        if existing.empty:
            return _empty_ts()
        # Return best-effort slice of existing
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        return _ensure_schema(ex[ex["Date"] >= cutoff].reset_index(drop=True))

    # Merge and dedupe by Date
    combined = (
        pd.concat([existing, new], ignore_index=True)
        .drop_duplicates(subset="Date")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    _save_parquet(combined, cache_path)
    return _ensure_schema(combined[combined["Date"].dt.date >= cutoff].reset_index(drop=True))


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


# Track cache file mtimes to detect updates
_CACHE_FILE_MTIMES: Dict[str, float] = {}


@lru_cache(maxsize=512)
def _load_meta_timeseries_cached(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    """LRU-backed loader for Meta timeseries."""
    cache = str(meta_timeseries_cache_path(ticker, exchange))
    return _rolling_cache(
        fetch_meta_timeseries,
        cache,
        {"ticker": ticker, "exchange": exchange},
        days,
        ticker=ticker,
        exchange=exchange,
    )


def load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    """Load Meta timeseries with in-process caching and mutation safety."""
    global OFFLINE_MODE

    # If offline mode toggles, clear in-memory cache
    if OFFLINE_MODE != config.offline_mode:
        OFFLINE_MODE = config.offline_mode
        _load_meta_timeseries_cached.cache_clear()
        _CACHE_FILE_MTIMES.clear()

    path = meta_timeseries_cache_path(ticker, exchange)
    mtime = path.stat().st_mtime if path.exists() else 0.0
    prev = _CACHE_FILE_MTIMES.get(str(path))
    if prev is not None and prev != mtime:
        _load_meta_timeseries_cached.cache_clear()
    _CACHE_FILE_MTIMES[str(path)] = mtime

    return _load_meta_timeseries_cached(ticker, exchange, days).copy()


# ──────────────────────────────────────────────────────────────
# In-process LRU for *ranges* (no duplicate IO per request)
# ──────────────────────────────────────────────────────────────
@lru_cache(maxsize=512)
def _memoized_range_cached(
    ticker: str,
    exchange: str,
    start_iso: str,
    end_iso: str,
) -> pd.DataFrame:
    global OFFLINE_MODE

    start_date = datetime.fromisoformat(start_iso).date()
    end_date = datetime.fromisoformat(end_iso).date()
    span_days = (end_date - start_date).days + 1
    lookback = (date.today() - end_date).days
    days_needed = span_days + lookback

    if OFFLINE_MODE:
        cache_path = str(meta_timeseries_cache_path(ticker, exchange))
        existing = _load_parquet(cache_path)
        # When running in offline mode we normally expect a cached copy to be
        # present.  If it's missing, fall back to the live loader so tests can
        # still exercise the conversion logic with monkeypatched fetchers.
        if not existing.empty:
            ex = existing.copy()
            ex["Date"] = ex["Date"].dt.date
            mask = (ex["Date"] >= start_date) & (ex["Date"] <= end_date)
            return _ensure_schema(ex.loc[mask].reset_index(drop=True))
        logger.warning("Offline mode: no cached data for %s.%s", ticker, exchange)

        # Temporarily disable offline mode so the live loader can fetch data.
        prev_offline_mode = config.offline_mode
        prev_global = OFFLINE_MODE
        try:
            config.offline_mode = False
            OFFLINE_MODE = False
            superset = load_meta_timeseries(ticker, exchange, days_needed)
        finally:
            config.offline_mode = prev_offline_mode
            OFFLINE_MODE = prev_global
    else:
        # Either not in offline mode or cache miss above – fetch from the standard
        # loader, which callers are free to monkeypatch in tests.
        superset = load_meta_timeseries(ticker, exchange, days_needed)
    if superset.empty or "Date" not in superset.columns:
        return _empty_ts()

    mask = (superset["Date"].dt.date >= start_date) & (superset["Date"].dt.date <= end_date)
    return _ensure_schema(superset.loc[mask].reset_index(drop=True))


def _memoized_range(
    ticker: str,
    exchange: str,
    start_iso: str,
    end_iso: str,
) -> pd.DataFrame:
    """LRU-cached range fetch that returns a copy to prevent mutation."""
    return _memoized_range_cached(ticker, exchange, start_iso, end_iso).copy()


def _convert_to_gbp(df: pd.DataFrame, ticker: str, exchange: str, start: date, end: date) -> pd.DataFrame:
    """Convert OHLC prices to GBP if needed based on instrument currency."""

    meta = get_instrument_meta(f"{ticker}.{exchange}")
    currency = meta.get("currency") or EXCHANGE_TO_CCY.get((exchange or "").upper(), "GBP")

    if currency in ("GBP", "GBX") or df.empty:
        return df

    if OFFLINE_MODE:
        path = _cache_path("fx", f"{currency}.parquet")
        try:
            fx = pd.read_parquet(path)
            fx["Date"] = pd.to_datetime(fx["Date"])
        except Exception as exc:
            logger.debug("FX cache read miss (%s): %s", path, exc)
            fx = pd.DataFrame(columns=["Date", "Rate"])

        if fx.empty and getattr(config, "fx_proxy_url", None):
            try:
                url = f"{config.fx_proxy_url.rstrip('/')}/{currency}"
                params = {"start": start.isoformat(), "end": end.isoformat()}
                resp = requests.get(url, params=params, timeout=5)
                if resp.ok:
                    fx = pd.DataFrame(resp.json())
                    fx["Date"] = pd.to_datetime(fx["Date"])
            except Exception as exc:
                logger.warning("FX proxy fetch failed for %s: %s", currency, exc)

        # If we still have no rates, fall back to the normal fetcher.  Tests
        # monkeypatch this function so no real network calls occur.
        if fx.empty:
            try:
                fx = fetch_fx_rate_range(currency, start, end).copy()
                fx["Date"] = pd.to_datetime(fx["Date"])
            except Exception as exc:
                raise ValueError(f"Offline mode: no FX rates for {currency}") from exc

        mask = (fx["Date"].dt.date >= start) & (fx["Date"].dt.date <= end)
        fx = fx.loc[mask]
        if fx.empty:
            raise ValueError(f"Offline mode: FX cache lacks range for {currency}")
    else:
        fx = fetch_fx_rate_range(currency, start, end).copy()
        if fx.empty:
            return df
        fx["Date"] = pd.to_datetime(fx["Date"])

    fx["Rate"] = pd.to_numeric(fx["Rate"], errors="coerce")
    merged = df.merge(fx, on="Date", how="left")
    merged["Rate"] = merged["Rate"].ffill().bfill()
    for col in ["Open", "High", "Low", "Close"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
            merged[f"{col}_gbp"] = merged[col] * merged["Rate"]
    return merged.drop(columns=["Rate"])


# ──────────────────────────────────────────────────────────────
# Public helper: explicit date range
# ──────────────────────────────────────────────────────────────
def load_meta_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    for offset in range(0, 5):  # try same day, 1-day back, 2-day back...
        s = start_date - timedelta(days=offset)
        e = end_date - timedelta(days=offset)
        df = _memoized_range(ticker, exchange, s.isoformat(), e.isoformat())
        if not df.empty:
            try:
                df = _convert_to_gbp(df, ticker, exchange, s, e)
            except ValueError as exc:
                logger.warning("Skipping FX conversion for %s.%s: %s", ticker, exchange, exc)
                return _empty_ts()
            return df
    return _empty_ts()


def has_cached_meta_timeseries(ticker: str, exchange: str) -> bool:
    path = meta_timeseries_cache_path(ticker, exchange)
    return path.exists() and path.stat().st_size > 0


def meta_timeseries_cache_path(ticker: str, exchange: str) -> Path:
    return Path(_cache_path("meta", f"{ticker.upper()}_{exchange.upper()}.parquet"))


# NOTE: keep arg order to avoid breaking existing callers
def get_price_for_date(exchange, ticker, date, field="Close"):
    """
    Returns float or None. Applies instrument scaling overrides.
    """
    df = load_meta_timeseries_range(ticker=ticker, exchange=exchange, start_date=date, end_date=date)
    if df.empty:
        return None
    scale = get_scaling_override(ticker, exchange, requested_scaling=None)
    df = apply_scaling(df, scale)
    try:
        return float(df.iloc[0][field])
    except Exception:
        return None
