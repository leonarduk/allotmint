"""
Timeseries parquet-cache layer (local path, EFS, or S3).

Set ``TIMESERIES_CACHE_BASE`` or ``config.timeseries_cache_base`` to control
where the parquet files live, e.g.

    export TIMESERIES_CACHE_BASE=data/timeseries          # local dev
    export TIMESERIES_CACHE_BASE=/mnt/efs/timeseries     # ECS / Lambda
    export TIMESERIES_CACHE_BASE=s3://allotmint-cache/ts # S3 bucket
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict
from urllib.parse import quote

import boto3
import pandas as pd
import requests
from botocore.exceptions import BotoCoreError, ClientError

from backend.common.instruments import get_instrument_meta
from backend.config import config
from backend.logging_setup import sanitise_log_value

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

# Simple counter for fetch failures – useful for lightweight monitoring.
_FAILED_FETCH_COUNT = 0

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


_sanitize_for_log = sanitise_log_value


def _empty_ts() -> pd.DataFrame:
    """Guaranteed-schema empty frame."""
    return pd.DataFrame(columns=EXPECTED_COLS)


def _ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Make sure DF has the expected columns; if not, return an empty DF with schema.
    Normalises 'Date' to datetime64[ms] for consistent resolution across pandas
    versions: pandas 3.x infers datetime64[s] when converting Python date objects
    via pd.to_datetime, while pandas 2.x infers datetime64[ns]. Pinning to ms
    matches the resolution pyarrow writes to parquet by default and keeps
    assert_frame_equal comparisons stable regardless of the code path that
    produced the Date values.
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
    dates = pd.to_datetime(df["Date"], errors="coerce")
    # Strip timezone info before casting: .astype("datetime64[ms]") raises
    # TypeError on tz-aware Series. All callers in this module produce tz-naive
    # timestamps, but this guard future-proofs against upstream tz-aware feeds.
    # Use tz_convert(None) not tz_localize(None): since pandas 2.0 calling
    # tz_localize(None) on tz-aware data raises TypeError; tz_convert(None)
    # converts to UTC then removes the timezone label.
    if dates.dt.tz is not None:
        logger.warning(
            "Timeseries 'Date' column is tz-aware (%s); converting to UTC and "
            "stripping timezone before casting to datetime64[ms].",
            dates.dt.tz,
        )
        dates = dates.dt.tz_convert(None)
    df["Date"] = dates.astype("datetime64[ms]")
    df = df.dropna(subset=["Date"])
    # Return only expected columns in expected order (stable)
    return df[EXPECTED_COLS]


# ──────────────────────────────────────────────────────────────
# Cache base (local path, EFS, or S3)
# ──────────────────────────────────────────────────────────────

# ``config.timeseries_cache_base`` may be ``None`` if configuration failed to
# load or the setting is omitted.  Callers must explicitly provide a base via
# the ``TIMESERIES_CACHE_BASE`` environment variable or configuration.
_CACHE_BASE: str | None = os.getenv("TIMESERIES_CACHE_BASE") or config.timeseries_cache_base
if _CACHE_BASE is None:
    raise ValueError(
        "Timeseries cache base is not configured; set TIMESERIES_CACHE_BASE or config.timeseries_cache_base."
    )


def _cache_path(*parts: str) -> str:
    """Build a full path / S3 key under the configured base."""
    if _CACHE_BASE is None:
        raise ValueError(
            "Timeseries cache base is not configured; set TIMESERIES_CACHE_BASE or config.timeseries_cache_base."
        )
    if _CACHE_BASE.startswith("s3://"):
        return "/".join([_CACHE_BASE, *parts])
    return str(Path(_CACHE_BASE, *parts))


def _ensure_local_dir(path: str) -> None:
    if _CACHE_BASE is None:
        raise ValueError(
            "Timeseries cache base is not configured; set TIMESERIES_CACHE_BASE or config.timeseries_cache_base."
        )
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

    try:
        new = fetch_func(**fetch_args)
    except Exception as exc:  # pragma: no cover - defensive path
        global _FAILED_FETCH_COUNT
        _FAILED_FETCH_COUNT += 1
        fetch_name = getattr(fetch_func, "__name__", repr(fetch_func))
        logger.warning(
            "Timeseries fetch failed for %s.%s via %s; serving cached data if available: %s",
            ticker,
            exchange,
            fetch_name,
            exc,
        )
        logger.debug("Timeseries fetch failure details", exc_info=True)
        if existing.empty:
            return _empty_ts()
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        return _ensure_schema(ex[ex["Date"] >= cutoff].reset_index(drop=True))
    new = _ensure_schema(new)

    if new.empty:
        logger.warning("No new timeseries data for %s.%s", ticker, exchange)
        if existing.empty:
            return _empty_ts()
        # Return best-effort slice of existing
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        return _ensure_schema(ex[ex["Date"] >= cutoff].reset_index(drop=True))

    # Merge and dedupe by Date, skipping empty/all-NA frames to avoid
    # pandas concat dtype warnings and object coercion
    frames = [df for df in (existing, new) if not df.empty and df.notna().any().any()]
    if not frames:
        logger.warning("No timeseries data for %s.%s", ticker, exchange)
        return _empty_ts()
    combined = (
        pd.concat(frames, ignore_index=True).drop_duplicates(subset="Date").sort_values("Date").reset_index(drop=True)
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


@lru_cache(maxsize=1)
def _s3_client():
    """Return the shared boto3 S3 client used by cache metadata checks."""
    return boto3.client("s3")


def _split_s3_cache_uri(cache: str) -> tuple[str, str] | None:
    without_scheme = cache[len("s3://") :]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        logger.warning("Invalid S3 timeseries cache path: %s", cache)
        return None
    return bucket, key


def _s3_object_mtime(cache: str) -> float:
    """Return the S3 object's LastModified timestamp for cache invalidation."""

    parsed = _split_s3_cache_uri(cache)
    if parsed is None:
        return 0.0
    bucket, key = parsed

    try:
        resp = _s3_client().head_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - defensive AWS path
        logger.warning("Unable to read S3 cache metadata for %s: %s", cache, exc)
        return 0.0

    last_modified = resp.get("LastModified")
    if not hasattr(last_modified, "timestamp"):
        logger.warning("S3 cache metadata for %s is missing LastModified", cache)
        return 0.0
    return float(last_modified.timestamp())


def _invalidate_meta_caches_if_stale(ticker: str, exchange: str) -> None:
    """Clear both meta LRUs when the backing file's mtime has changed."""
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        mtime = _s3_object_mtime(cache)
    else:
        p = Path(cache)
        mtime = p.stat().st_mtime if p.exists() else 0.0
    prev = _CACHE_FILE_MTIMES.get(cache)
    if prev is not None and prev != mtime:
        _load_meta_timeseries_cached.cache_clear()
        _memoized_range_cached.cache_clear()
    _CACHE_FILE_MTIMES[cache] = mtime


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
        _memoized_range_cached.cache_clear()
        _CACHE_FILE_MTIMES.clear()

    _invalidate_meta_caches_if_stale(ticker, exchange)
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
        # present. If it's missing we should not attempt any live fetches here
        # and simply return an empty frame. Higher-level helpers may decide to
        # temporarily disable offline mode and retry if they want a fallback.
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


def _convert_to_base_currency(
    df: pd.DataFrame,
    ticker: str,
    exchange: str,
    start: date,
    end: date,
    base_currency: str,
) -> pd.DataFrame:
    """Convert OHLC prices to ``base_currency`` if needed."""

    meta = get_instrument_meta(f"{ticker}.{exchange}")
    currency = meta.get("currency") or EXCHANGE_TO_CCY.get((exchange or "").upper(), "GBP")
    base_currency = (base_currency or "GBP").upper()

    if currency in (base_currency, "GBX") or df.empty:
        return df

    def _load_rates(curr: str) -> pd.DataFrame:
        curr = (curr or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", curr):
            logger.warning("Invalid/unsupported FX currency code: %s", _sanitize_for_log(curr))
            return pd.DataFrame(columns=["Date", "Rate"])

        if OFFLINE_MODE:
            path = _cache_path("fx", f"{curr}.parquet")
            try:
                fx = pd.read_parquet(path)
                fx["Date"] = pd.to_datetime(fx["Date"])
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("FX cache read miss (%s): %s", path, exc)
                fx = pd.DataFrame(columns=["Date", "Rate"])

            if fx.empty and getattr(config, "fx_proxy_url", None):
                try:
                    safe_curr = quote(curr, safe="")
                    url = f"{config.fx_proxy_url.rstrip('/')}/{safe_curr}"
                    params = {"start": start.isoformat(), "end": end.isoformat()}
                    resp = requests.get(url, params=params, timeout=5)
                    if resp.ok:
                        fx = pd.DataFrame(resp.json())
                        fx["Date"] = pd.to_datetime(fx["Date"])
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("FX proxy fetch failed for %s: %s", curr, exc)

            if fx.empty:
                try:
                    fx = fetch_fx_rate_range(curr, "GBP", start, end).copy()
                    if fx.empty:
                        raise ValueError(f"Offline mode: no FX rates for {curr}")

                    fx["Date"] = pd.to_datetime(fx["Date"])
                except Exception as exc:
                    raise ValueError(f"Offline mode: no FX rates for {curr}") from exc

            mask = (fx["Date"].dt.date >= start) & (fx["Date"].dt.date <= end)
            fx = fx.loc[mask]
            if fx.empty:
                raise ValueError(f"Offline mode: FX cache lacks range for {curr}")
        else:
            fx = fetch_fx_rate_range(curr, "GBP", start, end).copy()
            if fx.empty:
                return pd.DataFrame()
            fx["Date"] = pd.to_datetime(fx["Date"])

        fx["Rate"] = pd.to_numeric(fx["Rate"], errors="coerce")
        return fx

    fx_from_instr = _load_rates(currency)
    if fx_from_instr.empty:
        return df

    if base_currency == "GBP":
        fx = fx_from_instr[["Date", "Rate"]]
    else:
        fx_base = _load_rates(base_currency)
        if fx_base.empty:
            return df
        fx = fx_from_instr.merge(fx_base, on="Date", how="left", suffixes=("_inst", "_base"))
        fx["Rate"] = fx["Rate_inst"] / fx["Rate_base"]
        fx = fx[["Date", "Rate"]]

    merged = df.merge(fx, on="Date", how="left")
    merged["Rate"] = merged["Rate"].ffill().bfill()
    base_lower = base_currency.lower()
    for col in ["Open", "High", "Low", "Close"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
            merged[f"{col}_{base_lower}"] = merged[col] * merged["Rate"]
    return merged.drop(columns=["Rate"])


# ──────────────────────────────────────────────────────────────
# Public helper: explicit date range
# ──────────────────────────────────────────────────────────────
def load_meta_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
    _allow_fallback: bool = True,
    base_currency: str = "GBP",
) -> pd.DataFrame:
    global OFFLINE_MODE
    _invalidate_meta_caches_if_stale(ticker, exchange)
    for offset in range(0, 5):  # try same day, 1-day back, 2-day back...
        s = start_date - timedelta(days=offset)
        e = end_date - timedelta(days=offset)
        df = _memoized_range(ticker, exchange, s.isoformat(), e.isoformat())
        if not df.empty:
            try:
                df = _convert_to_base_currency(df, ticker, exchange, s, e, base_currency)
            except ValueError as exc:
                logger.warning("Skipping FX conversion for %s.%s: %s", ticker, exchange, exc)
                return _empty_ts()
            return df

    if _allow_fallback and (OFFLINE_MODE or config.offline_mode):
        prev_offline_mode = config.offline_mode
        prev_global = OFFLINE_MODE
        try:
            config.offline_mode = False
            OFFLINE_MODE = False
            _memoized_range_cached.cache_clear()
            return load_meta_timeseries_range(
                ticker,
                exchange,
                start_date,
                end_date,
                _allow_fallback=False,
                base_currency=base_currency,
            )
        finally:
            config.offline_mode = prev_offline_mode
            OFFLINE_MODE = prev_global

    return _empty_ts()


def _s3_cache_object_exists(cache: str) -> bool:
    """Return whether an S3 cache object exists using a shared boto3 client.

    Non-404 AWS errors are treated as cache misses after error logging so local
    fallback paths can continue when credentials, networking, or IAM are broken.
    """

    parsed = _split_s3_cache_uri(cache)
    if parsed is None:
        return False
    bucket, key = parsed

    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        logger.error("Unable to check S3 timeseries cache object %s: %s", cache, exc)
        return False
    except BotoCoreError as exc:
        logger.error("AWS client error checking S3 timeseries cache object %s: %s", cache, exc)
        return False
    return True


def has_cached_meta_timeseries(ticker: str, exchange: str) -> bool:
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        return _s3_cache_object_exists(cache)
    p = Path(cache)
    return p.exists() and p.stat().st_size > 0


def meta_timeseries_cache_path(ticker: str, exchange: str) -> str:
    return _cache_path("meta", f"{ticker.upper()}_{exchange.upper()}.parquet")


# NOTE: keep arg order to avoid breaking existing callers
def get_price_for_date(exchange, ticker, date, field="Close", base_currency: str = "GBP"):
    """
    Returns float or None. Applies instrument scaling overrides.
    """
    df = load_meta_timeseries_range(
        ticker=ticker,
        exchange=exchange,
        start_date=date,
        end_date=date,
        base_currency=base_currency,
    )
    if df.empty:
        return None
    scale = get_scaling_override(ticker, exchange, requested_scaling=None)
    df = apply_scaling(df, scale)
    try:
        return float(df.iloc[0][field])
    except Exception:
        return None
