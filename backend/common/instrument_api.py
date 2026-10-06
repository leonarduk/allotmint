# backend/common/instrument_api.py
"""
Instrument-level helpers for AllotMint
=====================================

Public API
----------

- timeseries_for_ticker(ticker, days=365, start_date=None, end_date=None)
- batch_timeseries_for_tickers(tickers, days=365, include_mini=False)
- dedupe_tickers(tickers)   - blank/case-insensitive-duplicate removal
- positions_for_ticker(group_slug, ticker)
- instrument_summaries_for_group(group_slug)   - used by InstrumentTable
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from backend.common.constants import ACCOUNTS, HOLDINGS, OWNER, PRICE_CHANGE_WINDOWS
from backend.common.group_portfolio import build_group_portfolio
from backend.common.holding_utils import load_latest_prices
from backend.common.instruments import list_group_definitions
from backend.common.numeric_utils import is_nan
from backend.common.portfolio_utils import get_security_meta, list_all_unique_tickers
from backend.common.ticker_utils import split_ticker
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import (
    has_cached_meta_timeseries,
    is_cache_only,
    load_meta_timeseries_range,
    map_in_caller_context,
    register_meta_cache_clearer,
)
from backend.timeseries.fetch_meta_timeseries import run_all_tickers
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_period
from backend.utils.pricing_dates import PricingDateCalculator
from backend.utils.timeseries_helpers import (
    _nearest_weekday,
    apply_scaling,
    get_scaling_override,
    resolve_date_range,
)

logger = logging.getLogger(__name__)

# Per-ticker price/history lookups (price_change_pct, _close_on,
# _price_and_changes) are I/O-bound (S3 reads through backend.timeseries.cache,
# occasionally a live provider fetch on a cache miss) and independent across
# tickers, so functions that loop over a portfolio's tickers fan them out
# across a small thread pool instead of fetching one ticker at a time -- for
# a 10-ticker group that was ~6-12s sequential (each of the S3 mtime-check +
# read pair adds up), confirmed live against production. The underlying cache
# layer already uses locks around its shared LRU/mtime state (see
# backend/timeseries/cache.py's _S3_MTIME_CACHE_LOCK etc.), so this is safe
# to parallelize without further changes there. Bounded rather than
# one-thread-per-ticker to avoid overwhelming a small Lambda's CPU/network
# allocation on a large portfolio.
_PRICE_FETCH_MAX_WORKERS = 8


def _build_exchange_map(tickers: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for t in tickers:
        sym, ex = (t.split(".", 1) + [None])[:2]
        if ex:
            mapping[sym.upper()] = ex.upper()
            continue
        meta = get_security_meta(t)
        ex_meta = meta.get("exchange") if meta else None
        if ex_meta:
            mapping[sym.upper()] = ex_meta.upper()
    return mapping


def _resolve_full_ticker(ticker: str, latest: Dict[str, float]) -> Optional[tuple[str, str]]:
    """
    Return `(symbol, exchange)` for *ticker*.
    Prefer exact key in latest prices; otherwise consult cached portfolio metadata.
    """
    t = (ticker or "").upper()
    if not t:
        return None
    if "." in t:
        # split_ticker maps a padded LSE EPIC ("BP.") to ("BP", "L") so it
        # shares a cache key with "BP.L" instead of an empty exchange (#8600).
        sym, ex = split_ticker(t)
        if sym and ex:
            return sym, ex
        return None
    base = t
    for k in latest.keys():
        sym, ex = (k.split(".", 1) + [None])[:2]
        if sym == base and ex:
            return sym, ex
    ex = _TICKER_EXCHANGE_MAP.get(base)
    if ex:
        return base, ex
    return None


# Fallback helper for group-by metadata
def _coerce_group_value(
    value: Any,
    catalogue: Mapping[str, Mapping[str, Any]],
    *,
    treat_as_id: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None

    if isinstance(value, Mapping):
        raw_id = value.get("id") or value.get("grouping_id")
        raw_name = value.get("name")
        ident = str(raw_id).strip() if raw_id is not None else None
        if ident:
            name, slug = _coerce_group_value(ident, catalogue, treat_as_id=True)
            if isinstance(raw_name, str) and raw_name.strip():
                return raw_name.strip(), slug or ident
            return name, slug
        if isinstance(raw_name, str):
            return _coerce_group_value(raw_name, catalogue, treat_as_id=treat_as_id)
        return None, None

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None, None

        if treat_as_id:
            definition = catalogue.get(trimmed)
            if definition:
                ident = str(definition.get("id") or trimmed)
                name_val = definition.get("name")
                if isinstance(name_val, str) and name_val.strip():
                    return name_val.strip(), ident
                return ident, ident
            return trimmed, trimmed

        definition = catalogue.get(trimmed)
        if definition:
            ident = str(definition.get("id") or trimmed)
            name_val = definition.get("name")
            if isinstance(name_val, str) and name_val.strip():
                return name_val.strip(), ident
            return ident, ident

        for definition in catalogue.values():
            name_val = definition.get("name")
            if isinstance(name_val, str) and name_val.strip().lower() == trimmed.lower():
                ident = str(definition.get("id") or trimmed)
                return name_val.strip(), ident

        return trimmed, None

    return None, None


def _resolve_grouping_details(
    *sources: Optional[Mapping[str, Any]],
    current: Optional[Any] = None,
) -> Tuple[Optional[str], Optional[str]]:
    catalogue = list_group_definitions()

    name, slug = _coerce_group_value(current, catalogue)
    if name:
        return name, slug

    for src in sources:
        if not src:
            continue
        name, slug = _coerce_group_value(src.get("grouping_id"), catalogue, treat_as_id=True)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("grouping"), catalogue)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("sector"), catalogue)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("currency"), catalogue)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("region"), catalogue)
        if name:
            return name, slug

    return None, None


def _derive_grouping(*sources: Optional[Mapping[str, Any]], current: Optional[Any] = None) -> Optional[str]:
    """Return the first non-empty grouping/sector/currency/region from the metadata."""

    name, _ = _resolve_grouping_details(*sources, current=current)
    return name


# Load once; callers can restart process to refresh or we can add a reload later.
_ALL_TICKERS: List[str] = list_all_unique_tickers()
_TICKER_EXCHANGE_MAP: Dict[str, str] = _build_exchange_map(_ALL_TICKERS)

# Global cache for the last known price of each instrument.  This is populated
# on demand to avoid network access during module import.  ``create_app`` primes
# this in a background task unless ``config.skip_snapshot_warm`` is set.
_LATEST_PRICES: Dict[str, float] = {}

MIN_PRICE_THRESHOLD = 1e-2
MAX_CHANGE_PCT = float(getattr(config, "max_change_pct", 500.0))


def prime_latest_prices() -> None:
    """Populate ``_LATEST_PRICES`` from timeseries data.

    This may involve network requests.  Callers should ensure it runs in a
    background task if they don't want to block startup.
    """

    global _LATEST_PRICES
    if config.skip_snapshot_warm:
        _LATEST_PRICES = {}
        return
    _LATEST_PRICES = load_latest_prices(_ALL_TICKERS)


def update_latest_prices_from_snapshot(snapshot: Dict[str, Dict[str, Any]]) -> None:
    """Seed ``_LATEST_PRICES`` using an existing price snapshot.

    This avoids network access and provides reasonable defaults until
    :func:`prime_latest_prices` runs.
    """

    global _LATEST_PRICES
    _LATEST_PRICES = {
        t: float(info.get("last_price"))
        for t, info in snapshot.items()
        if isinstance(info, dict) and info.get("last_price") is not None
    }


# ───────────────────────────────────────────────────────────────
# Historical close series (GBP where native is GBP, e.g., LSE)
# ───────────────────────────────────────────────────────────────
def timeseries_for_ticker(
    ticker: str,
    days: int = 365,
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """Return recent price history for ``ticker``.

    The payload contains the full series under ``prices`` plus shorter windows
    (7/30/180 days) under ``mini``.  This keeps the original behaviour
    (callers previously only consumed the list) while exposing pre-sliced
    subsets that are convenient for sparkline charts.

    When *start_date* or *end_date* are provided they override the window
    calculated from *days*.  The primary filter is pushed to the data layer via
    :func:`load_meta_timeseries_range`.  A secondary Python-level pass is still
    applied after loading because the cache layer may shift the window backward
    by up to four days to accommodate weekends/holidays; that pass enforces the
    originally-requested bounds precisely.
    """
    empty_payload: Dict[str, Any] = {
        "prices": [],
        "mini": {"7": [], "30": [], "180": []},
    }

    if not ticker:
        return empty_payload

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return empty_payload
    sym, ex = resolved

    # Only fetch if not cached
    if not has_cached_meta_timeseries(sym, ex):
        try:
            # Best-effort priming; safe to ignore failures since we fall back anyway.
            run_all_tickers([sym], exchange=ex)
        except Exception:
            pass

    ts_start, ts_end = resolve_date_range(days, start_date=start_date, end_date=end_date)

    if ts_start > ts_end:
        logger.warning(
            "timeseries_for_ticker: inverted date range for %s (%s > %s); returning empty",
            sanitise_log_value(ticker),
            sanitise_log_value(str(ts_start)),
            sanitise_log_value(str(ts_end)),
        )
        return empty_payload

    df = load_meta_timeseries_range(sym, ex, start_date=ts_start, end_date=ts_end)
    if df is None or df.empty:
        return empty_payload

    # Normalize column names
    if "Date" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"Date": "date"})
    if "Close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"Close": "close"})
    if "Close_gbp" in df.columns and "close_gbp" not in df.columns:
        df = df.rename(columns={"Close_gbp": "close_gbp"})
    if "close" not in df.columns and "close_gbp" in df.columns:
        df["close"] = df["close_gbp"]

    if {"date", "close"} - set(df.columns):
        return empty_payload

    # LSE data sources often report price in pence without saying so; apply the
    # same curated per-ticker correction the single-instrument route applies
    # (see get_scaling_override) so this shared helper -- used by the batch
    # endpoint and by portfolio.py's instrument_detail -- doesn't silently
    # diverge from it.
    scale = get_scaling_override(sym, ex, None)
    if scale != 1.0:
        df = apply_scaling(df, scale)
        if "close_gbp" in df.columns:
            df["close_gbp"] = pd.to_numeric(df["close_gbp"], errors="coerce") * scale

    ts_start_iso = ts_start.isoformat()
    ts_end_iso = ts_end.isoformat()
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        rd = r["date"]
        if isinstance(rd, (dt.datetime, dt.date)):
            rd = rd.date().isoformat() if isinstance(rd, dt.datetime) else rd.isoformat()
        # Enforce the explicit date contract: load_meta_timeseries_range may
        # shift the window backward by up to 4 days to find data across
        # weekends/holidays, so we re-apply the originally-requested bounds here.
        if rd < ts_start_iso or rd > ts_end_iso:
            continue
        # Some cached rows carry a Volume but no OHLC (e.g. an incomplete
        # upstream fetch for that day) -- ``close`` is NaN in that case.
        # Such a row has no usable price, so drop it rather than emit a
        # ``nan`` float: json.dumps rejects NaN outright (ValueError: Out of
        # range float values are not JSON compliant), which crashes response
        # serialization for the whole batch, not just this one ticker/day.
        if is_nan(r["close"]):
            continue
        close_val = float(r["close"])
        close_gbp_raw = r.get("close_gbp", close_val)
        if is_nan(close_gbp_raw):
            # Converted series, but no FX rate for this date (#9759): a
            # missing GBP price, never the native close passed off as GBP.
            continue
        close_gbp_val = float(close_gbp_raw)
        out.append({"date": rd, "close": close_val, "close_gbp": close_gbp_val})
    mini = {
        "7": out[-7:],
        "30": out[-30:],
        "180": out[-180:],
    }
    return {"prices": out, "mini": mini}


def dedupe_tickers(tickers: Sequence[str]) -> List[str]:
    """Drop blanks and case-insensitive duplicates, keeping the caller's spelling.

    The first spelling of each ticker wins.  Callers key their own bookkeeping off
    the strings they sent, so echoing a normalised (e.g. upper-cased) form back
    would leave them unable to match a response to a request.
    """
    seen: set[str] = set()
    unique: List[str] = []
    for raw in tickers:
        cleaned = (raw or "").strip()
        if not cleaned:
            continue
        key = cleaned.upper()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def batch_timeseries_for_tickers(
    tickers: Sequence[str],
    days: int = 365,
    *,
    include_mini: bool = False,
) -> Dict[str, Any]:
    """Resolve price history for many tickers in one pass.

    Returns ``{"instruments": {...}, "empty": [...], "unknown": [...]}`` where the
    three buckets **partition** the de-duplicated request: every ticker appears in
    exactly one of them, and their union is the input.  A ticker missing from all
    three, or counted in two, would corrupt the caller's "no price history" tally,
    so the partition is part of the contract rather than an implementation detail.

    The buckets distinguish two failures that look alike but are not:

    ``unknown``
        The ticker does not resolve to a ``(symbol, exchange)`` pair at all —
        a bare symbol with no exchange suffix that also isn't in the price
        snapshot, portfolio metadata, or ``_TICKER_EXCHANGE_MAP``.
    ``empty``
        The ticker resolves, but no price rows exist in the requested window.
        ``_resolve_full_ticker`` treats resolution as structural: any
        ``SYMBOL.EX`` string splits into a ``(symbol, exchange)`` pair whether
        or not that instrument actually exists, so a typo like ``BOGUS.L``
        lands here, not in ``unknown``.

    Collapsing them would regress the consolidated "no price history" notice,
    which is about the second case only.

    ``mini`` (the 7/30/180-day slices) is omitted unless *include_mini* is set:
    those rows duplicate the tail of ``prices``, and a batch response is exactly
    where that redundancy is multiplied by the number of holdings.
    """
    unique = dedupe_tickers(tickers)

    instruments: Dict[str, Any] = {}
    empty: List[str] = []
    unknown: List[str] = []

    for ticker in unique:
        if not _resolve_full_ticker(ticker, _LATEST_PRICES):
            unknown.append(ticker)
            continue

        series = timeseries_for_ticker(ticker, days=days)
        prices = series.get("prices") or []
        if not prices:
            empty.append(ticker)
            continue

        payload: Dict[str, Any] = {"prices": prices}
        if include_mini:
            payload["mini"] = series.get("mini", {})
        instruments[ticker] = payload

    return {"instruments": instruments, "empty": empty, "unknown": unknown}


def intraday_timeseries_for_ticker(ticker: str) -> Dict[str, Any]:
    """Return ~48 hours of intraday prices for ``ticker``.

    Falls back to end-of-day prices when the instrument type does not support
    intraday quotes or when intraday fetching fails.
    """

    empty_payload: Dict[str, Any] = {"prices": [], "last_price_time": None}
    if not ticker:
        return empty_payload

    meta = get_security_meta(ticker) or {}
    inst_type = meta.get("instrument_type") or meta.get("instrumentType")
    if inst_type and inst_type.lower() in {"pension"}:
        daily = timeseries_for_ticker(ticker, days=2)["prices"]
        prices = [{"timestamp": f"{p['date']}T00:00:00", "price": float(p["close"])} for p in daily]
        last_time = prices[-1]["timestamp"] if prices else None
        return {"prices": prices, "last_price_time": last_time}

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return empty_payload
    sym, ex = resolved

    df = None
    for interval in ("5m", "15m"):
        try:
            df = fetch_yahoo_timeseries_period(sym, ex, period="5d", interval=interval, normalize=False)
            if not df.empty:
                break
        except Exception:
            df = None
    if df is None or df.empty or "Date" not in df.columns:
        daily = timeseries_for_ticker(ticker, days=2)["prices"]
        prices = [{"timestamp": f"{p['date']}T00:00:00", "price": float(p["close"])} for p in daily]
        last_time = prices[-1]["timestamp"] if prices else None
        return {"prices": prices, "last_price_time": last_time}

    df = df.copy()
    # Ensure datetime comparison uses a consistent timezone by converting to UTC
    # and dropping tzinfo so we can compare against a naive UTC cutoff.
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=48)
    df = df[df["Date"] >= cutoff]

    # This raw Yahoo fetch is never scaled, unlike the two fallback branches
    # above (which now go through timeseries_for_ticker's scaling correction).
    # Without this, a ticker in data/scaling_overrides.json would jump ~100x
    # depending on whether Yahoo's intraday fetch happened to succeed.
    scale = get_scaling_override(sym, ex, None)
    if scale != 1.0:
        df = apply_scaling(df, scale)
        if "Close_gbp" in df.columns:
            df["Close_gbp"] = pd.to_numeric(df["Close_gbp"], errors="coerce") * scale

    col = "Close_gbp" if "Close_gbp" in df.columns else "Close"

    prices = [{"timestamp": r["Date"].to_pydatetime().isoformat(), "price": float(r[col])} for _, r in df.iterrows()]
    last_time = prices[-1]["timestamp"] if prices else None
    return {"prices": prices, "last_price_time": last_time}


# ───────────────────────────────────────────────────────────────
# Last price + %-changes helpers
# ───────────────────────────────────────────────────────────────


_CLOSE_ON_CACHE_MAXSIZE = 2048
_close_on_cache: "OrderedDict[tuple[str, str, dt.date], float]" = OrderedDict()
# Guards _close_on_cache's mutations only (check/insert/evict), not the
# load_meta_timeseries_range call on a miss -- unlike lru_cache's C
# implementation, OrderedDict.move_to_end/popitem aren't atomic across a
# read-modify-write sequence, so concurrent threads (FastAPI's sync-endpoint
# threadpool) could otherwise race on the dict itself. A miss still lets two
# threads compute the same (ticker, date) concurrently and both write the
# same value -- wasted duplicate work, not a correctness issue, the same
# trade-off any unlocked check-then-compute cache makes (#8232 review round 5).
_close_on_cache_lock = threading.Lock()


def _close_on_cache_only(sym: str, ex: str, snap: dt.date) -> Optional[float]:
    """Memoized body of ``_close_on``, used only inside a ``cache_only()`` block (#8211).

    ``price_change_pct`` calls ``_close_on`` twice per ticker (yesterday, and
    ``days`` ago), and the same ticker often recurs across multiple accounts/
    holdings within one portfolio build and across repeated page requests for
    the same owner in this long-lived process -- each call otherwise pays the
    full ``load_meta_timeseries_range`` round trip (the per-(ticker,range) LRU,
    ``apply_date_range``, ``_ensure_schema``, and an uncached FX merge in
    ``_convert_to_base_currency``) for what is conceptually one row. Only
    memoized for cache-only reads (page requests): a live/background-refresh
    read is specifically asking for fresh data, which this process-lifetime
    cache must not intercept. Registered with
    ``backend.timeseries.cache.register_meta_cache_clearer`` so a stale
    underlying file still invalidates this cache the same way it invalidates
    the timeseries module's own.

    Takes the already-``_nearest_weekday``-snapped date, not the caller's raw
    ``d`` -- keying on the raw date would give a Saturday and its Sunday (or
    the Friday they both resolve to) three separate cache entries for what is
    the same underlying row, defeating the point of memoizing (#8232 review).

    A ``None`` result is deliberately **not** memoized, unlike a plain
    ``lru_cache`` -- for either way ``_close_on_impl`` can produce one:

    - No cached row for this day at all: ``load_meta_timeseries_range`` queues
      the ticker on ``refresh_queue``, and that queueing is itself
      de-duplicated/cooldown-gated there. Caching the ``None`` here as well
      would silently swallow that queueing for every subsequent lookup of the
      same day for the rest of this process's lifetime, including once real
      data finally lands -- there being no file to have an mtime on yet,
      ``_invalidate_meta_caches_if_stale`` has nothing to bust this entry with
      in the meantime (#8232 review, ``test_reports_cache_only.py``).
    - A row exists but its close is NaN: there's no refresh-queue concern
      here, so skipping the memo just means a missed optimization (the NaN
      row gets re-read on the next lookup) rather than a correctness risk --
      not worth a second code path to special-case, since a NaN close for an
      already-cached day is rare (#8232 review round 7).
    """
    key = (sym, ex, snap)
    with _close_on_cache_lock:
        if key in _close_on_cache:
            _close_on_cache.move_to_end(key)
            return _close_on_cache[key]
    result = _close_on_impl(sym, ex, snap)
    if result is not None:
        with _close_on_cache_lock:
            _close_on_cache[key] = result
            _close_on_cache.move_to_end(key)
            if len(_close_on_cache) > _CLOSE_ON_CACHE_MAXSIZE:
                _close_on_cache.popitem(last=False)
    return result


def _clear_close_on_cache() -> None:
    with _close_on_cache_lock:
        _close_on_cache.clear()


_close_on_cache_only.cache_clear = _clear_close_on_cache  # type: ignore[attr-defined]


def _close_on_impl(sym: str, ex: str, snap: dt.date) -> Optional[float]:
    """Return close price for ``sym.ex`` ticker on the (already weekend-snapped) date ``snap``."""
    df = load_meta_timeseries_range(sym, ex, start_date=snap, end_date=snap)
    if df is None or df.empty:
        return None
    col = "close_gbp" if "close_gbp" in df.columns else ("Close_gbp" if "Close_gbp" in df.columns else None)
    if col is None:
        col = "close" if "close" in df.columns else ("Close" if "Close" in df.columns else None)
    if not col:
        return None
    price = float(df[col].iloc[0])
    return None if is_nan(price) else price


def _close_on(sym: str, ex: str, d: dt.date) -> Optional[float]:
    """Return close price for ``sym.ex`` ticker on date ``d`` if available."""
    snap = _nearest_weekday(d, forward=False)
    if is_cache_only():
        return _close_on_cache_only(sym, ex, snap)
    return _close_on_impl(sym, ex, snap)


register_meta_cache_clearer(_close_on_cache_only.cache_clear)


def price_change_pct(ticker: str, days: int) -> Optional[float]:
    """Return % change from ``days`` ago to yesterday's close for ``ticker``."""
    today = dt.date.today()
    yday = today - dt.timedelta(days=1)

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return None

    sym, ex = resolved
    px_now = _close_on(sym, ex, yday)
    px_then = _close_on(sym, ex, yday - dt.timedelta(days=days))
    if px_now is None or px_then is None or px_then == 0:
        return None
    if px_then < MIN_PRICE_THRESHOLD:
        logger.warning(
            "price_change_pct: px_then %.4f below threshold for %s",
            px_then,
            sanitise_log_value(ticker),
        )
        return None
    pct = (px_now / px_then - 1.0) * 100.0
    if abs(pct) > MAX_CHANGE_PCT:
        logger.warning(
            "price_change_pct: change %.2f%% exceeds max %.2f%% for %s",
            pct,
            MAX_CHANGE_PCT,
            sanitise_log_value(ticker),
        )
        return None
    return pct


def _resolve_last_price_date(calc: PricingDateCalculator) -> dt.date:
    """Return the appropriate last price date for the calculator context."""

    if calc.today.weekday() == 0:  # Monday
        return calc.today - dt.timedelta(days=1)
    return calc.reporting_date


def top_movers(
    tickers: List[str],
    days: int,
    limit: int = 10,
    *,
    min_weight: float = 0.0,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return top gainers and losers for ``tickers`` over ``days``.

    Parameters
    ----------
    min_weight:
        Minimum portfolio weight (in percent) required for a ticker to be
        included.  Set to ``0`` to disable filtering.
    weights:
        Optional mapping of ``ticker -> weight_percent`` used for filtering.
    """

    calc = PricingDateCalculator(today=dt.date.today(), weekday_func=_nearest_weekday)
    last_price_date = _resolve_last_price_date(calc)
    rows: List[Dict[str, Any]] = []
    anomalies: List[str] = []

    candidates = [t for t in tickers if not (min_weight and weights and weights.get(t, 0.0) < min_weight)]

    def _row_or_anomaly(t: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Return (row, None) on success, (None, ticker) as an anomaly, or
        (None, None) when the ticker doesn't resolve at all (silently
        skipped, matching the original sequential loop's behaviour)."""

        change = price_change_pct(t, days)
        if change is None:
            return None, t
        resolved = _resolve_full_ticker(t, _LATEST_PRICES)
        if not resolved:
            return None, None
        sym, ex = resolved
        full = f"{sym}.{ex}" if ex else sym
        last_px = _close_on(sym, ex, last_price_date)
        meta = get_security_meta(full) or {}
        return (
            {
                "ticker": full,
                "name": meta.get("name", full),
                "change_pct": change,
                "last_price_gbp": last_px,
                "last_price_date": last_price_date.isoformat(),
                "instrument_type": meta.get("instrument_type"),
            },
            None,
        )

    # See _PRICE_FETCH_MAX_WORKERS above: price_change_pct/_close_on are the
    # slow, I/O-bound part, and independent per ticker, so fetch them
    # concurrently rather than one ticker at a time.
    if candidates:
        with ThreadPoolExecutor(max_workers=min(_PRICE_FETCH_MAX_WORKERS, len(candidates))) as pool:
            for row, anomaly in map_in_caller_context(pool, _row_or_anomaly, candidates):
                if row is not None:
                    rows.append(row)
                elif anomaly is not None:
                    anomalies.append(anomaly)

    pos = sorted(
        [r for r in rows if r["change_pct"] > 0],
        key=lambda r: r["change_pct"],
        reverse=True,
    )
    neg = sorted(
        [r for r in rows if r["change_pct"] < 0],
        key=lambda r: r["change_pct"],
    )
    return {"gainers": pos[:limit], "losers": neg[:limit], "anomalies": anomalies}


@lru_cache(maxsize=2048)
def _price_and_changes(ticker: str) -> Dict[str, Any]:
    """
    Return last price and common percentage changes for ``ticker``.
    """
    calc = PricingDateCalculator(today=dt.date.today(), weekday_func=_nearest_weekday)
    last_price_date = _resolve_last_price_date(calc)

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return {
            "last_price_gbp": None,
            "last_price_date": None,
            "last_price_time": None,
            "is_stale": True,
            **{key: None for key in PRICE_CHANGE_WINDOWS},
        }
    sym, ex = resolved

    from backend.common import portfolio_utils as pu  # local import

    snap = pu._PRICE_SNAPSHOT.get(ticker.upper()) or pu._PRICE_SNAPSHOT.get(sym)
    if isinstance(snap, dict) and snap.get("last_price") is not None:
        last_px = snap.get("last_price")
        last_time = snap.get("last_price_time")
        is_stale = bool(snap.get("is_stale", False))
    else:
        last_px = _close_on(sym, ex, last_price_date)
        last_time = None
        is_stale = True

    return {
        "last_price_gbp": last_px,
        "last_price_date": last_price_date.isoformat(),
        "last_price_time": last_time,
        "is_stale": is_stale,
        **{key: price_change_pct(ticker, days) for key, days in PRICE_CHANGE_WINDOWS.items()},
    }


# ───────────────────────────────────────────────────────────────
# Positions by ticker
# ───────────────────────────────────────────────────────────────
def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    """
    Return enriched positions for the given ticker across a group.
    Uses the already-enriched holdings from group_portfolio (owner added onto each acct).
    """
    gp = build_group_portfolio(group_slug)
    rows: List[Dict[str, Any]] = []

    def _matches(q: str, held: str) -> bool:
        qU, hU = (q or "").upper(), (held or "").upper()
        return hU == qU or hU.split(".", 1)[0] == qU.split(".", 1)[0]

    for acct in gp.get(ACCOUNTS, []):
        owner = acct.get(OWNER)
        acct_type = acct.get("account_type")
        currency = acct.get("currency")
        for h in acct.get(HOLDINGS, []):
            if _matches(ticker, h.get("ticker")) and (h.get("units") or 0):
                rows.append(
                    {
                        "owner": owner,
                        "account_type": acct_type,
                        "currency": currency,
                        "units": h.get("units", 0.0),
                        "current_price_gbp": h.get("current_price_gbp") or h.get("price"),
                        "market_value_gbp": h.get("market_value_gbp"),
                        "book_cost_basis_gbp": h.get("cost_basis_gbp", 0.0),
                        "effective_cost_basis_gbp": h.get("effective_cost_basis_gbp", 0.0),
                        "gain_gbp": h.get("gain_gbp", 0.0),
                        "gain_pct": h.get("gain_pct"),
                        "days_held": h.get("days_held"),
                        "sell_eligible": h.get("sell_eligible"),
                        "days_until_eligible": h.get("days_until_eligible"),
                        "eligible_on": h.get("eligible_on"),
                        "next_eligible_sell_date": h.get("next_eligible_sell_date"),
                    }
                )
    return rows


# ───────────────────────────────────────────────────────────────
# Instrument table rows
# ───────────────────────────────────────────────────────────────
def instrument_summaries_for_group(group_slug: str) -> List[Dict[str, Any]]:
    """
    Aggregate holdings in *group_slug* into per-ticker summary for InstrumentTable.
    Adds last price + 7d/30d % changes (as-of yesterday) via the same pipeline.
    """
    gp = build_group_portfolio(group_slug)
    by_ticker: Dict[str, Dict[str, Any]] = {}
    # Market value of holdings with a known gain, per ticker (#8471).
    known_gain_mv: Dict[str, float] = {}

    for acct in gp.get(ACCOUNTS, []):
        for h in acct.get(HOLDINGS, []):
            tkr = (h.get("ticker") or "").strip()
            name = (h.get("name") or "").strip()
            if not tkr or not name:
                continue

            entry = by_ticker.setdefault(
                tkr,
                {
                    "ticker": tkr,
                    "name": name,
                    "units": 0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp": 0.0,
                },
            )
            entry["units"] += float(h.get("units") or 0.0)
            market_value = float(h.get("market_value_gbp") or 0.0)
            entry["market_value_gbp"] += market_value
            # A holding with an unknown cost has gain_gbp None (#8471). Leave it
            # out of both the gain and the implied cost (market value - gain),
            # or its market value would count as cost and dilute gain_pct.
            # Tracked outside the response entries so it can never leak.
            if h.get("gain_gbp") is not None:
                entry["gain_gbp"] += float(h["gain_gbp"])
                known_gain_mv[tkr] = known_gain_mv.get(tkr, 0.0) + market_value

    # Decorate with last price + changes. _price_and_changes is the slow,
    # I/O-bound part (see _PRICE_FETCH_MAX_WORKERS above) -- fetch it for
    # every ticker concurrently rather than one at a time.
    price_tickers = [tkr for tkr in by_ticker if tkr]
    price_and_changes: Dict[str, Dict[str, Any]] = {}
    if price_tickers:
        with ThreadPoolExecutor(max_workers=min(_PRICE_FETCH_MAX_WORKERS, len(price_tickers))) as pool:
            price_and_changes = dict(zip(price_tickers, map_in_caller_context(pool, _price_and_changes, price_tickers)))

    for tkr, entry in by_ticker.items():
        if not tkr:
            continue
        meta = get_security_meta(tkr) or {}
        entry.setdefault("asset_class", meta.get("asset_class"))
        entry.setdefault("industry", meta.get("industry") or meta.get("sector"))
        entry.setdefault("region", meta.get("region"))
        entry.setdefault("sector", meta.get("sector"))
        grouping_name, grouping_id = _resolve_grouping_details(meta, entry, current=entry.get("grouping"))
        if grouping_id:
            entry["grouping_id"] = grouping_id
        if grouping_name:
            entry["grouping"] = grouping_name
        entry.update(price_and_changes[tkr])
        if tkr in known_gain_mv:
            cost = known_gain_mv[tkr] - entry["gain_gbp"]
            entry["gain_pct"] = (entry["gain_gbp"] / cost * 100.0) if cost else None
        else:
            entry["gain_pct"] = None

    return sorted(by_ticker.values(), key=lambda r: r["market_value_gbp"], reverse=True)
