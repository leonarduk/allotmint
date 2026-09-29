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
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict
from urllib.parse import quote

import boto3
import numpy as np
import pandas as pd
import requests
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.common.instruments import get_instrument_meta
from backend.config import config
from backend.logging_setup import sanitise_log_value

# ──────────────────────────────────────────────────────────────
# Remote fetchers
# ──────────────────────────────────────────────────────────────
from backend.timeseries import refresh_queue
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.utils.fx_rates import (
    fallback_fx_rate_range,
    fetch_fx_rate_range,
    fetch_fx_rate_range_live,
)
from backend.utils.timeseries_helpers import (
    _nearest_weekday,
    apply_date_range,
    apply_scaling,
    get_scaling_override,
)

OFFLINE_MODE = config.offline_mode

# Per-request "read the parquet cache, never call a price source" switch
# (#7898). Page requests (group/owner portfolio builds) turn it on so their
# latency never depends on Yahoo/Stooq; the background snapshot refresh and
# the admin/timeseries endpoints stay live and keep the parquet files current.
# A ContextVar, not a module flag, so it is scoped to the calling request and
# thread and can't leak into the background refresh.
_CACHE_ONLY: ContextVar[bool] = ContextVar("timeseries_cache_only", default=False)


@contextmanager
def cache_only() -> Iterator[None]:
    """Serve meta timeseries from the on-disk/S3 cache only inside this block."""
    token = _CACHE_ONLY.set(True)
    try:
        yield
    finally:
        _CACHE_ONLY.reset(token)


def is_cache_only() -> bool:
    return _CACHE_ONLY.get()


logger = logging.getLogger(__name__)

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

    Performance (#8137): when the input already conforms exactly (Date already
    datetime64[ms], no nulls, columns already EXPECTED_COLS in order -- true
    for every already-validated slice this function re-validates on every one
    of the ~1400+ per-(ticker, date-range) lookups against the #8113 warm
    cache), this returns the input object unchanged rather than doing the
    equivalent-but-redundant astype/dropna/reindex work. Every caller in this
    module that needs mutation safety already wraps its own LRU layer with an
    explicit ``.copy()`` (``_memoized_range``, ``load_meta_timeseries``), so
    returning the same object here does not introduce new aliasing risk --
    verified directly, not assumed (see the #8137 mutation-safety test).

    Contract: this function may return its input object unchanged. Callers
    that don't already own an exclusive copy of ``df`` and need to mutate the
    result must copy it first -- exactly the same rule that already applied
    to the input ``df`` itself, since this function has always mutated
    ``df["Date"]`` in place when coercion is needed.
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
    # `pd.to_datetime(..., errors="coerce")` is expensive even when the column
    # is already a proper datetime64 dtype: pandas' `should_cache` heuristic
    # iterates every element to decide whether to memoize parsed values,
    # which dominates runtime on the large (thousands-of-rows) per-ticker
    # parquet histories this function re-validates on every cache read (see
    # #8095 -- this is the actual hot path behind the slow sector/region
    # aggregation endpoints, not a live network call). Skip the conversion
    # entirely when there is nothing to parse; only fall back to
    # `pd.to_datetime` for inputs that genuinely need parsing (raw strings,
    # ``datetime.date`` objects, etc.).
    if pd.api.types.is_datetime64_any_dtype(df["Date"]):
        dates = df["Date"]
    else:
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
    # Both `.astype("datetime64[ms]")` and `.dropna()` are no-ops when the
    # column already has the target dtype and no nulls -- true on every call
    # for a frame that has already passed through this function once (e.g. a
    # slice of an already-validated warm-cache frame, per #8137). Skipping
    # them when they'd change nothing avoids re-running dropna's full-frame
    # mask + reindex machinery, which profiling showed is over half of this
    # function's cost on such calls (2.39s of 4.45s for 1453 calls on a
    # 64-row sliced frame -- see #8137).
    if dates.dtype != "datetime64[ms]":
        df["Date"] = dates.astype("datetime64[ms]")
    elif dates is not df["Date"]:
        df["Date"] = dates
    if df["Date"].hasnans:
        df = df.dropna(subset=["Date"])
    # Return only expected columns in expected order (stable). Skip the
    # reindex when the columns already match exactly -- this getitem is a
    # full column-by-column copy, and profiling showed it dominates what's
    # left once the astype/dropna skips above apply (see #8137).
    if list(df.columns) == EXPECTED_COLS:
        return df
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


@lru_cache(maxsize=512)
def _load_meta_parquet_cached(path: str) -> pd.DataFrame:
    """Warm, process-level cache of a validated *meta* timeseries parquet file (#8105).

    ``_load_parquet`` re-reads and re-validates (``_ensure_schema``) the full
    per-ticker history on every call. The per-(ticker, days)/(ticker, range)
    LRUs on ``_load_meta_timeseries_cached``/``_memoized_range_cached`` only
    dedupe *identical* repeat lookups; different holdings for the same owner
    routinely request slightly different windows against the same ticker,
    which busts those keys but still hits the same underlying file. Caching
    the parquet read itself, keyed only by path, lets every such lookup for a
    ticker within a process share one disk read + one schema validation.

    This is also wired in as ``_rolling_cache``'s ``loader`` for the live meta
    path (``_load_meta_timeseries_cached``), which is the *write* path: it
    merges fetched rows into the ``existing`` frame this function returns and
    may save the result. That makes in-place mutation of ``existing`` a real
    hazard, not just a read-only-caller concern -- see the DeepSeek PR review
    on #8105. It was audited line by line: every place ``_rolling_cache`` (and
    the ``_merge_fetched`` helper it calls) touches ``existing`` -- ``.copy()``,
    boolean ``.loc[mask]`` selection, ``pd.concat``, ``.sort_values()``/
    ``.reset_index()`` -- is called without ``inplace=True`` and produces a new
    DataFrame rather than writing back into the original buffers; there is no
    ``existing[...] = ...``/``existing.loc[...] = ...`` anywhere in this
    module. ``test_rolling_cache_does_not_mutate_shared_loader_cache`` in
    ``tests/test_timeseries_cache_merge.py`` pins this down empirically: it
    primes this cache, drives a real write through ``_rolling_cache`` using
    this function as the loader, and asserts the still-cached object is
    unchanged afterward. So callers -- both the read-only page-request paths
    and ``_rolling_cache``'s own write path -- only ever read from the
    returned frame (slicing/copying, never mutating in place -- see
    ``apply_date_range``'s own docs too), and sharing the same object across
    all of them is safe.

    Invalidated by ``_invalidate_meta_caches_if_stale`` on exactly the same
    mtime check that already clears ``_load_meta_timeseries_cached`` and
    ``_memoized_range_cached`` (#7877), so this can never serve data staler
    than those two would.
    """
    return _load_parquet(path)


# ──────────────────────────────────────────────────────────────
# Rolling parquet cache (disk/S3)
# ──────────────────────────────────────────────────────────────
# Columns whose change on an already-cached date counts as a correction.
_VALUE_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _value_matrix(df: pd.DataFrame) -> np.ndarray:
    return df[_VALUE_COLS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)


def _merge_fetched(existing: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Merge ``new`` into ``existing`` by calendar date.

    Returns ``(combined, changed)``. A fetched row replaces the cached row for
    the same date when any value column differs (a source correcting a price),
    but only if the fetched row has a Close -- a row without one carries no
    usable correction. Differences within float noise (rtol=1e-9) and NaN on
    both sides count as equal, so re-fetching identical data leaves ``changed``
    False and the parquet (and its mtime) untouched (#7877, #7914).

    Only ``_VALUE_COLS`` are compared. When a cached date is kept, its other
    columns (``Source``, ``Ticker``) are kept too, so a re-fetch that changes
    only ``Source`` does not update the stored provenance.
    """
    existing = existing.loc[~existing["Date"].dt.date.duplicated()]
    new = new.loc[~new["Date"].dt.date.duplicated(keep="last")]
    cached_rows = pd.Series(range(len(existing)), index=existing["Date"].dt.date)
    new_dates = new["Date"].dt.date
    overlap = new.loc[new_dates.isin(cached_rows.index).to_numpy()]
    added = new.loc[~new_dates.isin(cached_rows.index).to_numpy()]

    before = _value_matrix(existing.iloc[cached_rows[overlap["Date"].dt.date].to_numpy()])
    after = _value_matrix(overlap)
    differs = ~np.isclose(before, after, rtol=1e-9, atol=0.0, equal_nan=True).all(axis=1)
    corrected = overlap.loc[differs & overlap["Close"].notna().to_numpy()]

    kept = existing.loc[~existing["Date"].dt.date.isin(set(corrected["Date"].dt.date)).to_numpy()]
    frames = [df for df in (kept, corrected, added) if not df.empty and df.notna().any().any()]
    combined = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)
    return combined, not added.empty or not corrected.empty


def _rolling_cache(
    fetch_func: Callable[..., pd.DataFrame],
    cache_path: str,
    fetch_args: Dict,
    days: int,
    *,
    ticker: str,
    exchange: str,
    loader: Callable[[str], pd.DataFrame] | None = None,
) -> pd.DataFrame:

    logger.debug("Rolling cache: %s", cache_path)
    # Only look up to yesterday (we have close prices only)
    cutoff, today = _weekday_range(datetime.today().date() - timedelta(days=1), days)

    # Resolved here rather than as a default argument value so tests (and any
    # other caller) that monkeypatch the module-level ``_load_parquet`` still
    # take effect -- a default bound at def time would capture the original
    # function object instead.
    existing = (loader or _load_parquet)(cache_path)

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
            _sanitize_for_log(ticker),
            _sanitize_for_log(exchange),
            fetch_name,
            sanitise_log_value(exc),
        )
        logger.debug("Timeseries fetch failure details", exc_info=True)
        if existing.empty:
            return _empty_ts()
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        return _ensure_schema(ex[ex["Date"] >= cutoff].reset_index(drop=True))
    new = _ensure_schema(new)

    if new.empty:
        logger.warning("No new timeseries data for %s.%s", _sanitize_for_log(ticker), _sanitize_for_log(exchange))
        if existing.empty:
            return _empty_ts()
        # Return best-effort slice of existing
        ex = existing.copy()
        ex["Date"] = ex["Date"].dt.date
        return _ensure_schema(ex[ex["Date"] >= cutoff].reset_index(drop=True))

    if existing.empty:
        # Skip all-NA frames to avoid pandas concat dtype warnings/object coercion.
        if not new.notna().any().any():
            logger.warning("No timeseries data for %s.%s", _sanitize_for_log(ticker), _sanitize_for_log(exchange))
            return _empty_ts()
        combined = new.loc[~new["Date"].dt.date.duplicated(keep="last")].sort_values("Date").reset_index(drop=True)
        changed = True
    else:
        # Fetched rows win on date collisions only when they change a value, so
        # source corrections are persisted (#7914) while an identical re-fetch
        # is not: a no-op save still bumps the file's mtime, which makes
        # _invalidate_meta_caches_if_stale clear every ticker's LRU entries and
        # re-triggers this fetch on the next lookup (#7877).
        combined, changed = _merge_fetched(existing, new)
    if changed:
        _save_parquet(combined, cache_path)
    else:
        logger.debug(
            "No new or corrected rows for %s.%s; leaving cache untouched",
            sanitise_log_value(ticker),
            sanitise_log_value(exchange),
        )
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

# Remember S3 objects recently confirmed missing (HeadObject 404) so repeat
# lookups for the same permanently-uncached ticker within the TTL skip the
# live network round-trip. Without this, a request touching a delisted/
# unresolvable ticker (no data from any provider, ever) re-issues a
# synchronous S3 HeadObject call on every check -- observed in production to
# stack up into hundreds of calls within a single request and exhaust the
# Lambda's 30s timeout.
#
# Trade-off: during this 60s window, confirmed-missing objects will not
# trigger new HeadObject calls, so a ticker whose data appears in S3 shortly
# after an initial 404 (e.g. a delayed data load) can keep returning stale
# "not found" results for up to 60 seconds. Uses time.monotonic(), so the
# TTL resets on Lambda freeze/thaw -- acceptable, since a thawed instance
# re-checking S3 immediately is the safe direction to err in.
_S3_HEAD_MISS_TTL_SECONDS = 60.0
_S3_HEAD_MISS_CACHE: Dict[str, float] = {}
_S3_HEAD_MISS_CACHE_LOCK = threading.Lock()

# Remember the last confirmed mtime for S3 objects that DO exist, so repeat
# staleness checks for the same (present) ticker within the TTL skip the live
# HeadObject round-trip too. Without this, every load_meta_timeseries[_range]
# call -- including the 2-3 calls per ticker issued by price_change_pct/
# top_movers for a group's worth of holdings -- re-issues a synchronous S3
# HeadObject, turning a Movers/Instrument-page request into dozens of
# sequential network round trips and pushing it toward the Lambda timeout.
# See issue #5180 (regression of the #5093/#5103 cold-path symptom class).
#
# Trade-off: within this window a freshly-updated S3 object can be served
# from the previously-cached mtime, so ``_invalidate_meta_caches_if_stale``
# may miss an update for up to the TTL. That mirrors the negative-cache
# trade-off above and is acceptable for a value that changes at most once a
# day (end-of-day price refresh).
_S3_MTIME_TTL_SECONDS = 30.0
_S3_MTIME_CACHE: Dict[str, tuple[float, float]] = {}
_S3_MTIME_CACHE_LOCK = threading.Lock()


def _recently_confirmed_mtime(cache: str) -> float | None:
    with _S3_MTIME_CACHE_LOCK:
        entry = _S3_MTIME_CACHE.get(cache)
    if entry is None:
        return None
    mtime, fetched_at = entry
    if time.monotonic() - fetched_at < _S3_MTIME_TTL_SECONDS:
        return mtime
    return None


def _s3_object_recently_confirmed_missing(cache: str) -> bool:
    with _S3_HEAD_MISS_CACHE_LOCK:
        missed_at = _S3_HEAD_MISS_CACHE.get(cache)
    return missed_at is not None and time.monotonic() - missed_at < _S3_HEAD_MISS_TTL_SECONDS


def invalidate_s3_cache_metadata(cache: str) -> None:
    """Discard cached S3 existence metadata after a write or delete."""
    with _S3_HEAD_MISS_CACHE_LOCK:
        _S3_HEAD_MISS_CACHE.pop(cache, None)
    with _S3_MTIME_CACHE_LOCK:
        _S3_MTIME_CACHE.pop(cache, None)


# boto3's defaults (connect_timeout=60s, no read_timeout, 3 retries) let a
# single stalled HeadObject call block a cold Lambda invocation for minutes.
# These metadata checks are advisory (every caller already has a local/
# provider fallback on failure), so fail fast instead: a couple of seconds is
# enough for a healthy S3 endpoint, and one retry is enough to ride out a
# transient blip without risking the Lambda's own timeout budget.
_S3_CLIENT_CONFIG = Config(
    connect_timeout=3,
    read_timeout=5,
    retries={"max_attempts": 2, "mode": "standard"},
)


@lru_cache(maxsize=1)
def _s3_client():
    """Return the shared boto3 S3 client used by cache metadata checks."""
    return boto3.client("s3", config=_S3_CLIENT_CONFIG)


def _split_s3_cache_uri(cache: str) -> tuple[str, str] | None:
    without_scheme = cache[len("s3://") :]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        logger.warning("Invalid S3 timeseries cache path: %s", _sanitize_for_log(cache))
        return None
    return bucket, key


def _s3_head_object(cache: str, bucket: str, key: str, *, log_as_error: bool = False) -> dict | None:
    """Call HeadObject for ``cache``, maintaining the negative-cache as a side effect.

    Shared by :func:`_s3_object_mtime` and :func:`_s3_cache_object_exists` so
    the "miss -> record in negative cache -> return None" / "hit -> clear
    negative cache -> return response" behavior is defined once. A genuine
    404 registers the miss in ``_S3_HEAD_MISS_CACHE``; any other AWS error is
    logged (WARNING by default, matching the original :func:`_s3_object_mtime`
    behavior) and treated the same as a miss so callers fall back gracefully
    rather than raising. ``log_as_error=True`` preserves the ERROR severity
    :func:`_s3_cache_object_exists` used before this helper was extracted.
    Uses ``logger.warning``/``logger.error`` directly (not ``logger.log``) so
    the CWE-117 log-sanitization scanner (tests/test_log_sanitization_audit.py)
    still tracks these call sites.
    """
    try:
        resp = _s3_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            with _S3_HEAD_MISS_CACHE_LOCK:
                _S3_HEAD_MISS_CACHE[cache] = time.monotonic()
        elif log_as_error:
            logger.error(
                "Unable to read S3 cache metadata for %s: %s",
                _sanitize_for_log(cache),
                sanitise_log_value(exc),
            )
        else:
            logger.warning(
                "Unable to read S3 cache metadata for %s: %s",
                _sanitize_for_log(cache),
                sanitise_log_value(exc),
            )
        return None
    except BotoCoreError as exc:  # pragma: no cover - defensive AWS path
        if log_as_error:
            logger.error(
                "Unable to read S3 cache metadata for %s: %s",
                _sanitize_for_log(cache),
                sanitise_log_value(exc),
            )
        else:
            logger.warning(
                "Unable to read S3 cache metadata for %s: %s",
                _sanitize_for_log(cache),
                sanitise_log_value(exc),
            )
        return None

    with _S3_HEAD_MISS_CACHE_LOCK:
        _S3_HEAD_MISS_CACHE.pop(cache, None)
    return resp


def _s3_object_mtime(cache: str) -> float | None:
    """Return the S3 object's LastModified timestamp for cache invalidation.

    Returns ``None`` when the object was already confirmed missing within
    the negative-cache TTL, signalling the caller to skip invalidation
    entirely. Without this, the fallback ``0.0`` used for a genuine miss
    gets compared against the previously recorded mtime on every call,
    which is harmless on its own but leaves callers no way to distinguish
    "still missing" from "just went missing" and short-circuit further
    provider fallback work.
    """

    parsed = _split_s3_cache_uri(cache)
    if parsed is None:
        return 0.0
    bucket, key = parsed

    if _s3_object_recently_confirmed_missing(cache):
        return None

    cached_mtime = _recently_confirmed_mtime(cache)
    if cached_mtime is not None:
        return cached_mtime

    resp = _s3_head_object(cache, bucket, key)
    if resp is None:
        return 0.0

    last_modified = resp.get("LastModified")
    if not hasattr(last_modified, "timestamp"):
        logger.warning("S3 cache metadata for %s is missing LastModified", _sanitize_for_log(cache))
        return 0.0
    mtime = float(last_modified.timestamp())
    with _S3_MTIME_CACHE_LOCK:
        _S3_MTIME_CACHE[cache] = (mtime, time.monotonic())
    return mtime


# Other modules (backend.common.instrument_api's _close_on, backend.common.
# holding_utils's _get_price_for_date_scaled -- see #8211) memoize their own
# single-day price lookups on top of this module's caches. They can't import
# _invalidate_meta_caches_if_stale's callers directly without a circular
# import (they're already imported *by* this module's callers), so they
# register their lru_cache's .cache_clear here instead, and it's invoked
# alongside this module's own meta caches whenever any ticker's file goes
# stale -- the same coarse whole-cache-clear granularity _load_meta_timeseries_cached
# et al already use below, not a new invalidation model.
_EXTRA_META_CACHE_CLEARERS: list[Callable[[], None]] = []


def register_meta_cache_clearer(clear_fn: Callable[[], None]) -> None:
    """Register an external lru_cache to be cleared alongside this module's
    own meta caches whenever _invalidate_meta_caches_if_stale fires (#8211)."""
    _EXTRA_META_CACHE_CLEARERS.append(clear_fn)


def _invalidate_meta_caches_if_stale(ticker: str, exchange: str) -> None:
    """Clear both meta LRUs when the backing file's mtime has changed."""
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        mtime = _s3_object_mtime(cache)
        if mtime is None:
            # Confirmed-missing within the negative-cache TTL: the previous
            # miss already cleared the LRUs once, so there is nothing new
            # to invalidate and no reason to touch _CACHE_FILE_MTIMES.
            return
    else:
        p = Path(cache)
        mtime = p.stat().st_mtime if p.exists() else 0.0
    prev = _CACHE_FILE_MTIMES.get(cache)
    if prev is not None and prev != mtime:
        _load_meta_timeseries_cached.cache_clear()
        _memoized_range_cached.cache_clear()
        _load_meta_parquet_cached.cache_clear()
        for clear_fn in _EXTRA_META_CACHE_CLEARERS:
            clear_fn()
    _CACHE_FILE_MTIMES[cache] = mtime


def _last_close_target() -> date:
    """The latest close ``_rolling_cache`` fetches up to: the last weekday before today."""
    return _weekday_range(datetime.today().date() - timedelta(days=1), 0)[1]


def _queue_if_stale(ticker: str, exchange: str, existing: pd.DataFrame) -> None:
    """Queue a background refresh when a cache-only read found the parquet short of the last close (#7917)."""
    if existing.empty or existing["Date"].max().date() < _last_close_target():
        refresh_queue.enqueue(ticker, exchange)


def _cached_window(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    """The ``days`` window ``_rolling_cache`` would serve, read from cache only."""
    cutoff, today = _weekday_range(datetime.today().date() - timedelta(days=1), days)
    existing = _load_meta_parquet_cached(str(meta_timeseries_cache_path(ticker, exchange)))
    _queue_if_stale(ticker, exchange, existing)
    if existing.empty:
        return _empty_ts()
    dates = existing["Date"].dt.date
    return _ensure_schema(existing.loc[(dates >= cutoff) & (dates <= today)].reset_index(drop=True))


@lru_cache(maxsize=512)
def _load_meta_timeseries_cached(ticker: str, exchange: str, days: int, cache_only: bool = False) -> pd.DataFrame:
    """LRU-backed loader for Meta timeseries.

    ``cache_only`` is part of the LRU key so a cache-only read is never handed
    back to a live caller (e.g. the background refresh) as if it were fresh.
    """
    if cache_only:
        return _cached_window(ticker, exchange, days)
    cache = str(meta_timeseries_cache_path(ticker, exchange))
    return _rolling_cache(
        fetch_meta_timeseries,
        cache,
        {"ticker": ticker, "exchange": exchange},
        days,
        ticker=ticker,
        exchange=exchange,
        loader=_load_meta_parquet_cached,
    )


def load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
    """Load Meta timeseries with in-process caching and mutation safety."""
    global OFFLINE_MODE

    # If offline mode toggles, clear in-memory cache
    if OFFLINE_MODE != config.offline_mode:
        OFFLINE_MODE = config.offline_mode
        _load_meta_timeseries_cached.cache_clear()
        _memoized_range_cached.cache_clear()
        _load_meta_parquet_cached.cache_clear()
        _CACHE_FILE_MTIMES.clear()

    _invalidate_meta_caches_if_stale(ticker, exchange)
    return _load_meta_timeseries_cached(ticker, exchange, days, _CACHE_ONLY.get()).copy()


# ──────────────────────────────────────────────────────────────
# In-process LRU for *ranges* (no duplicate IO per request)
# ──────────────────────────────────────────────────────────────

# Floor for the `days` window _memoized_range_cached requests from
# load_meta_timeseries. A single ticker's price/change lookup
# (price_change_pct/_close_on, backend/common/instrument_api.py) issues up to
# 5 sub-calls for different single-day windows (last-price fallback, 7d
# before/after, 30d before/after); without a shared floor, each sub-call
# computes a different `days_needed` below and therefore a different
# _load_meta_timeseries_cached cache key, triggering a separate S3 read of
# the same underlying per-ticker parquet file. Flooring `days_needed` to this
# constant lets sub-calls within the window share one cache entry and one
# fetch. Set comfortably above the largest lookback in that call chain (30d
# change needs ~31 days back plus a few days of weekend-adjustment slack).
# `max()` below means a caller that legitimately needs a wider window (e.g.
# timeseries_for_ticker's default days=365, or scenario_tester's event-based
# lookups) is unaffected -- see issue #7565.
_MIN_CACHE_WINDOW_DAYS = 60


@lru_cache(maxsize=512)
def _memoized_range_cached(
    ticker: str,
    exchange: str,
    start_iso: str,
    end_iso: str,
    cache_only: bool = False,
) -> pd.DataFrame:
    # ``cache_only`` is part of the LRU key (see _load_meta_timeseries_cached)
    # and is acted on here directly, so key and behaviour can't disagree.
    global OFFLINE_MODE

    start_date = datetime.fromisoformat(start_iso).date()
    end_date = datetime.fromisoformat(end_iso).date()
    if cache_only:
        # Same read as the offline branch below, minus its live fallback.
        existing = _load_meta_parquet_cached(str(meta_timeseries_cache_path(ticker, exchange)))
        if end_date >= _last_close_target():
            # Only a read that wants the latest close queues a refresh; a
            # purely historical window is served whatever the cache's end.
            _queue_if_stale(ticker, exchange, existing)
        if existing.empty:
            return _empty_ts()
        return _ensure_schema(apply_date_range(existing, start_date, end_date))
    span_days = (end_date - start_date).days + 1
    lookback = (date.today() - end_date).days
    days_needed = max(span_days + lookback, _MIN_CACHE_WINDOW_DAYS)

    if OFFLINE_MODE:
        cache_path = str(meta_timeseries_cache_path(ticker, exchange))
        existing = _load_meta_parquet_cached(cache_path)
        # When running in offline mode we normally expect a cached copy to be
        # present. If it's missing we should not attempt any live fetches here
        # and simply return an empty frame. Higher-level helpers may decide to
        # temporarily disable offline mode and retry if they want a fallback.
        if not existing.empty:
            # apply_date_range returns rows with the original datetime64 Date dtype
            # (it normalises internally for comparison but doesn't mutate the column).
            # _ensure_schema always coerces Date to datetime64[ms] via pd.to_datetime,
            # so the dtype is safe regardless of what apply_date_range returns.
            return _ensure_schema(apply_date_range(existing, start_date, end_date))
        logger.warning("Offline mode: no cached data for %s.%s", _sanitize_for_log(ticker), _sanitize_for_log(exchange))

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

    return _ensure_schema(apply_date_range(superset, start_date, end_date))


def _memoized_range(
    ticker: str,
    exchange: str,
    start_iso: str,
    end_iso: str,
) -> pd.DataFrame:
    """LRU-cached range fetch that returns a copy to prevent mutation."""
    return _memoized_range_cached(ticker, exchange, start_iso, end_iso, _CACHE_ONLY.get()).copy()


# ──────────────────────────────────────────────────────────────
# FX parquet cache (#7917)
# ──────────────────────────────────────────────────────────────
# One file per currency, ``fx/{CCY}.parquet`` (Date, Rate = GBP per unit),
# under the timeseries cache base -- the same file the offline branch of
# _convert_to_base_currency reads. Only the refresh paths write it
# (refresh_prices on the schedule, the refresh queue locally); cache-only page
# requests read it so converting a USD holding never calls Yahoo inline.

# History seeded on the first refresh of a currency: cost-basis lookups can
# ask for a rate years back.
_FX_CACHE_HISTORY_DAYS = 3650

# How long a cache-only reader reuses its in-process copy of an FX file before
# re-reading it (an S3 GET on Lambda). Writes from this process drop the copy.
_FX_FRAME_TTL_SECONDS = 300.0
_FX_FRAMES: Dict[str, tuple[pd.DataFrame, float]] = {}
_FX_LOCK = threading.Lock()  # guards _FX_FRAMES only; never held across I/O
# Serialise read-merge-write per currency, so a hung fetch for one currency
# doesn't stall the others.
_FX_WRITE_LOCKS: Dict[str, threading.Lock] = {}


def _fx_write_lock(curr: str) -> threading.Lock:
    with _FX_LOCK:
        return _FX_WRITE_LOCKS.setdefault(curr, threading.Lock())


def instrument_currency(ticker: str, exchange: str) -> str:
    """The currency ``ticker.exchange`` is quoted in, from instrument metadata or the exchange."""
    meta = get_instrument_meta(f"{ticker}.{exchange}")
    return meta.get("currency") or EXCHANGE_TO_CCY.get((exchange or "").upper(), "GBP")


def _fx_cache_path(curr: str) -> str:
    return _cache_path("fx", f"{curr}.parquet")


def _read_fx_parquet(path: str) -> pd.DataFrame:
    try:
        fx = pd.read_parquet(path)
    except Exception as exc:
        logger.debug("FX cache read miss (%s): %s", sanitise_log_value(path), sanitise_log_value(exc))
        return pd.DataFrame(columns=["Date", "Rate"])
    fx["Date"] = pd.to_datetime(fx["Date"]).astype("datetime64[ms]")
    fx["Rate"] = pd.to_numeric(fx["Rate"], errors="coerce")
    return fx.dropna(subset=["Rate"]).sort_values("Date").reset_index(drop=True)


def _cached_fx_frame(curr: str) -> pd.DataFrame:
    now = time.monotonic()
    with _FX_LOCK:
        entry = _FX_FRAMES.get(curr)
    if entry is not None and now - entry[1] < _FX_FRAME_TTL_SECONDS:
        return entry[0]
    fx = _read_fx_parquet(_fx_cache_path(curr))
    with _FX_LOCK:
        _FX_FRAMES[curr] = (fx, now)
    return fx


def _cached_fx_rates(curr: str, start: date, end: date, *, ticker: str, exchange: str) -> pd.DataFrame:
    """Daily ``curr``->GBP rates for ``start``..``end`` from the FX cache, without fetching.

    Each day takes the latest cached rate on or before it; days before the
    first cached rate take that first rate. With no cache
    file at all this falls back to the same approximate constant a failed live
    fetch returns. Either way the ticker is queued so the refresh brings the
    FX cache up to date.
    """
    if curr == "GBP":
        # The GBP leg of a cross-currency conversion: the unit rate, no lookup.
        return pd.DataFrame({"Date": pd.date_range(start, end, freq="D").astype("datetime64[ms]"), "Rate": 1.0})
    cached = _cached_fx_frame(curr)
    if cached.empty or cached["Date"].max().date() < min(end, _last_close_target()):
        refresh_queue.enqueue(ticker, exchange)
    if cached.empty:
        fx = fallback_fx_rate_range(curr, "GBP", start, end)
        fx["Date"] = pd.to_datetime(fx["Date"])
        return fx
    days = pd.DataFrame({"Date": pd.date_range(start, end, freq="D").astype("datetime64[ms]")})
    fx = pd.merge_asof(days, cached[["Date", "Rate"]], on="Date", direction="backward")
    fx["Rate"] = fx["Rate"].fillna(cached["Rate"].iloc[0])
    return fx


def cached_fx_rate_to_gbp(curr: str) -> float | None:
    """Latest cached ``curr``->GBP rate from the FX cache, without fetching (#8028).

    For point-in-time conversions (a latest price, a portfolio's base
    currency) where there is no ticker to queue: a missing or stale cache
    queues the currency itself for a background FX refresh. Returns ``None``
    when nothing is cached, so the caller picks its own fallback.
    """
    curr = (curr or "").strip().upper()
    if curr == "GBP":
        return 1.0
    if not re.fullmatch(r"[A-Z]{3}", curr):
        return None
    cached = _cached_fx_frame(curr)
    if cached.empty or cached["Date"].max().date() < _last_close_target():
        refresh_queue.enqueue_fx(curr)
    if cached.empty:
        return None
    return float(cached["Rate"].iloc[-1])


def refresh_fx_cache(curr: str) -> bool:
    """Append live ``curr``->GBP rates to the FX cache; return whether the file changed.

    Fetches from the day after the last cached rate (or
    ``_FX_CACHE_HISTORY_DAYS`` back for a new currency) to today. Like
    _rolling_cache, a fetch that adds no dates leaves the file untouched.
    """
    curr = (curr or "").strip().upper()
    if curr in ("GBP", "GBX") or not re.fullmatch(r"[A-Z]{3}", curr):
        return False
    path = _fx_cache_path(curr)
    today = date.today()
    with _fx_write_lock(curr):
        existing = _read_fx_parquet(path)
        start = (
            existing["Date"].max().date() + timedelta(days=1)
            if not existing.empty
            else today - timedelta(days=_FX_CACHE_HISTORY_DAYS)
        )
        if start > today:
            return False
        live = fetch_fx_rate_range_live(curr, "GBP", start, today)
        if live.empty:
            return False
        live = live[["Date", "Rate"]].copy()
        live["Date"] = pd.to_datetime(live["Date"]).astype("datetime64[ms]")
        live["Rate"] = pd.to_numeric(live["Rate"], errors="coerce")
        frames = [f for f in (existing, live.dropna(subset=["Rate"])) if not f.empty]
        combined = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset="Date", keep="last")
            .sort_values("Date")
            .reset_index(drop=True)
        )
        if len(combined) == len(existing):
            return False
        _ensure_local_dir(path)
        combined.to_parquet(path, index=False)
        with _FX_LOCK:
            _FX_FRAMES.pop(curr, None)
    logger.info(
        "FX cache for %s now runs to %s",
        sanitise_log_value(curr),
        sanitise_log_value(combined["Date"].max().date()),
    )
    return True


def refresh_fx_cache_for_tickers(full_tickers: list[str]) -> None:
    """Refresh the FX cache for every non-GBP currency among ``full_tickers`` (``SYM.EXCH``)."""
    if config.offline_mode:
        return
    currencies = set()
    for full in full_tickers:
        sym, _, exch = (full or "").rpartition(".")
        if not sym:
            continue
        try:
            currencies.add(instrument_currency(sym, exch))
        except Exception as exc:
            logger.warning(
                "No currency for %s; skipping its FX refresh: %s", sanitise_log_value(full), sanitise_log_value(exc)
            )
    for curr in sorted(currencies):
        try:
            refresh_fx_cache(curr)
        except Exception as exc:
            logger.warning("FX cache refresh failed for %s: %s", sanitise_log_value(curr), sanitise_log_value(exc))


def _convert_to_base_currency(
    df: pd.DataFrame,
    ticker: str,
    exchange: str,
    start: date,
    end: date,
    base_currency: str,
) -> pd.DataFrame:
    """Convert OHLC prices to ``base_currency`` if needed."""

    currency = instrument_currency(ticker, exchange)
    base_currency = (base_currency or "GBP").upper()

    if currency in (base_currency, "GBX") or df.empty:
        return df

    def _load_rates(curr: str) -> pd.DataFrame:
        curr = (curr or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", curr):
            logger.warning("Invalid/unsupported FX currency code: %s", _sanitize_for_log(curr))
            return pd.DataFrame(columns=["Date", "Rate"])

        if _CACHE_ONLY.get():
            # Checked before offline mode: its cache miss goes to the FX proxy
            # and then Yahoo, which a page request must not do.
            fx = _cached_fx_rates(curr, start, end, ticker=ticker, exchange=exchange)
        elif OFFLINE_MODE:
            path = _fx_cache_path(curr)
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
                    logger.warning("FX proxy fetch failed for %s: %s", _sanitize_for_log(curr), sanitise_log_value(exc))

            if fx.empty:
                try:
                    fx = fetch_fx_rate_range(curr, "GBP", start, end).copy()
                    if fx.empty:
                        raise ValueError(f"Offline mode: no FX rates for {curr}")

                    fx["Date"] = pd.to_datetime(fx["Date"])
                except Exception as exc:
                    raise ValueError(f"Offline mode: no FX rates for {curr}") from exc

            fx = apply_date_range(fx, start, end)
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
def _converted_or_empty(
    df: pd.DataFrame, ticker: str, exchange: str, start: date, end: date, base_currency: str
) -> pd.DataFrame:
    try:
        return _convert_to_base_currency(df, ticker, exchange, start, end, base_currency)
    except ValueError as exc:
        logger.warning(
            "Skipping FX conversion for %s.%s: %s",
            sanitise_log_value(ticker),
            sanitise_log_value(exchange),
            sanitise_log_value(exc),
        )
        return _empty_ts()


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
            return _converted_or_empty(df, ticker, exchange, s, e, base_currency)

    if _CACHE_ONLY.get():
        # A cache-only read can't fetch the missing closes, so instead of
        # leaving the holding unpriced serve the last cached close on or
        # before end_date, however old; the read above has already queued
        # the ticker for a background refresh (#7917).
        history = _memoized_range(ticker, exchange, date.min.isoformat(), end_date.isoformat())
        if history.empty:
            return _empty_ts()
        last = history.tail(1).reset_index(drop=True)
        day = last["Date"].iloc[0].date()
        return _converted_or_empty(last, ticker, exchange, day, day, base_currency)

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

    if _s3_object_recently_confirmed_missing(cache):
        return False

    return _s3_head_object(cache, bucket, key, log_as_error=True) is not None


def has_cached_meta_timeseries(ticker: str, exchange: str) -> bool:
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        return _s3_cache_object_exists(cache)
    p = Path(cache)
    return p.exists() and p.stat().st_size > 0


def meta_timeseries_cache_path(ticker: str, exchange: str) -> str:
    return _cache_path("meta", f"{ticker.upper()}_{exchange.upper()}.parquet")


def load_cached_meta_timeseries_full(ticker: str, exchange: str) -> pd.DataFrame:
    """Read the full cached meta timeseries as-is, with no fetch or date filter.

    Unlike :func:`load_meta_timeseries_range`, this never triggers a live
    fetch and never dedupes/trims rows — it is intended for read-only
    diagnostics (e.g. data-quality checks) that need to see the raw cache
    contents, duplicates included.
    """
    return _load_parquet(meta_timeseries_cache_path(ticker, exchange))


def _local_cached_meta_filenames(base: str) -> list[str]:
    meta_dir = Path(base, "meta")
    if not meta_dir.is_dir():
        return []
    return [p.name for p in meta_dir.glob("*.parquet")]


def _s3_cached_meta_filenames(base: str) -> list[str]:
    without_scheme = base[len("s3://") :]
    bucket, _, prefix = without_scheme.partition("/")
    if not bucket:
        logger.warning("Invalid S3 timeseries cache base: %s", _sanitize_for_log(base))
        return []
    meta_prefix = f"{prefix.rstrip('/')}/meta/" if prefix else "meta/"
    names: list[str] = []
    try:
        paginator = _s3_client().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=meta_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".parquet"):
                    names.append(key.rsplit("/", 1)[-1])
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - defensive AWS path
        logger.error(
            "Unable to list S3 timeseries cache objects under %s: %s",
            _sanitize_for_log(meta_prefix),
            sanitise_log_value(exc),
        )
        return []
    return names


def list_cached_meta_tickers() -> list[tuple[str, str]]:
    """Return sorted (ticker, exchange) pairs for every cached meta timeseries file."""
    if _CACHE_BASE is None:
        return []
    if _CACHE_BASE.startswith("s3://"):
        filenames = _s3_cached_meta_filenames(_CACHE_BASE)
    else:
        filenames = _local_cached_meta_filenames(_CACHE_BASE)

    pairs: set[tuple[str, str]] = set()
    for name in filenames:
        if not name.endswith(".parquet"):
            continue
        stem = name[: -len(".parquet")]
        ticker, sep, exchange = stem.rpartition("_")
        if sep and ticker and exchange:
            pairs.add((ticker, exchange))
    return sorted(pairs)


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
