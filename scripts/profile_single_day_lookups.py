"""Measure the #8211 single-day price lookup fix against real cached data.

``_close_on`` (backend/common/instrument_api.py) and ``_get_price_for_date_scaled``
(backend/common/holding_utils.py) each request a single day as a full
``load_meta_timeseries_range`` window -- the per-(ticker,range) LRU,
``apply_date_range``, ``_ensure_schema`` and an uncached FX merge in
``_convert_to_base_currency``, all to extract one row. #8232 memoizes both
inside ``cache_only()`` (page requests only; a live/background-refresh read
is never served from the memo). This reproduces the before/after cost on a
real cached ticker, the same methodology #8105/#8113/#8127/#8131/#8137 used.

Requires the ``allotmint-data`` sibling checkout (``DATA_ROOT=../allotmint-data``)
with at least one warm ``timeseries/meta/<TICKER>_<EXCHANGE>.parquet`` file --
this does not fabricate data, since the point is to measure against a
realistic per-ticker history shape rather than a synthetic frame.

Usage::

    DATA_ROOT=../allotmint-data python -m scripts.profile_single_day_lookups [TICKER] [EXCHANGE]

``TICKER``/``EXCHANGE`` default to ``VOD``/``L`` (an arbitrary real fixture
from the `allotmint-data` set used throughout #8105/#8113/#8127/#8131/#8137).
"""

from __future__ import annotations

import datetime
import sys
import time

from backend.common import holding_utils, instrument_api
from backend.timeseries.cache import (
    _load_meta_parquet_cached,
    _load_meta_timeseries_cached,
    _memoized_range_cached,
    cache_only,
)

# Matches #8127/#8131's measured per-(ticker, date-range) call count for the
# worst-case owner ("steve") against the allotmint-data fixture set -- used
# here as the repeat count for a "same ticker looked up N times" simulation
# (multiple accounts holding the same ticker, or repeated page loads).
N_CALLS = 1453


def _last_cached_trading_day(ticker: str, exchange: str) -> datetime.date:
    full = _load_meta_parquet_cached(f"{_meta_cache_base()}/meta/{ticker}_{exchange}.parquet")
    if full.empty:
        raise SystemExit(
            f"No cached data for {ticker}.{exchange} -- set DATA_ROOT to allotmint-data."
        )
    return full["Date"].max().date()


def _meta_cache_base() -> str:
    from backend.timeseries.cache import _CACHE_BASE

    return _CACHE_BASE


def _reset_caches() -> None:
    instrument_api._close_on_cache.clear()
    holding_utils._unscaled_price_cache.clear()
    _memoized_range_cached.cache_clear()
    _load_meta_timeseries_cached.cache_clear()


def _time(label: str, fn) -> None:
    t0 = time.perf_counter()
    for _ in range(N_CALLS):
        fn()
    elapsed = time.perf_counter() - t0
    print(f"{label} x{N_CALLS}: {elapsed:.4f}s ({elapsed / N_CALLS * 1000:.4f}ms/call)")


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "VOD"
    exchange = sys.argv[2] if len(sys.argv) > 2 else "L"
    day = _last_cached_trading_day(ticker, exchange)
    print(f"{ticker}.{exchange} last cached trading day: {day}")

    with cache_only():
        _reset_caches()
        _time(
            "_close_on cold (no memo)", lambda: instrument_api._close_on_impl(ticker, exchange, day)
        )

        _reset_caches()
        instrument_api._close_on(ticker, exchange, day)  # warm the memo once
        _time("_close_on warm (memoized)", lambda: instrument_api._close_on(ticker, exchange, day))

        _reset_caches()
        _time(
            "_get_price_for_date_scaled cold (no memo)",
            lambda: holding_utils._load_unscaled_price_for_date_impl(ticker, exchange, day),
        )

        _reset_caches()
        holding_utils._get_price_for_date_scaled(ticker, exchange, day)  # warm the memo once
        _time(
            "_get_price_for_date_scaled warm (memoized)",
            lambda: holding_utils._get_price_for_date_scaled(ticker, exchange, day),
        )


if __name__ == "__main__":
    main()
