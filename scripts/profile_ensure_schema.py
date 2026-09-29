"""Reproduce the #8137 _ensure_schema profiling against real cached data.

Requires the ``allotmint-data`` sibling checkout (set ``DATA_ROOT``/
``config.yaml``'s ``paths.data_root`` to point at it) with at least one
warm ``timeseries/meta/<TICKER>_<EXCHANGE>.parquet`` file present -- this
does not fabricate data, since the whole point is to measure against a
realistic per-ticker history shape (row count, dtype) rather than a
synthetic frame.

Two modes:

- ``micro`` (default): isolates ``_ensure_schema``/``apply_date_range`` cost
  on one ticker's already-sliced frame, independent of any specific owner's
  portfolio shape.
- ``e2e``: the exact methodology #8105/#8113/#8127/#8131/#8137 all used --
  in-process ``cProfile`` around ``build_owner_portfolio`` + ``aggregate_by_sector``
  for a given owner, wrapped in ``cache_only()`` (the same context manager the
  real ``/portfolio/{owner}/sectors`` route uses) so it never depends on a
  live price fetch, with the per-``(ticker,range)`` LRUs cleared after a warm-up
  pass to reproduce "shared warm cache, first time this window is requested".
  ``cache_only()`` alone guarantees no live fetch regardless of
  ``market_data.offline_mode``'s config value -- no config change needed.

Usage::

    DATA_ROOT=../allotmint-data python -m scripts.profile_ensure_schema micro [TICKER_EXCHANGE]
    DATA_ROOT=../allotmint-data python -m scripts.profile_ensure_schema e2e [OWNER]

``TICKER_EXCHANGE`` defaults to ``VOD_L``; ``OWNER`` defaults to ``steve``
(both arbitrary real fixtures from the `allotmint-data` set used throughout
#8105/#8113/#8127/#8131/#8137).
"""

from __future__ import annotations

import cProfile
import datetime
import pstats
import sys
import time

from backend.timeseries.cache import (
    _CACHE_BASE,
    _ensure_schema,
    _load_meta_parquet_cached,
    _load_meta_timeseries_cached,
    _memoized_range_cached,
    cache_only,
)
from backend.utils.timeseries_helpers import apply_date_range

# Matches #8127/#8131's measured per-(ticker, date-range) call count for the
# worst-case owner ("steve") against the allotmint-data fixture set.
N_CALLS = 1453


def run_micro(ticker_exchange: str) -> None:
    path = f"{_CACHE_BASE}/meta/{ticker_exchange}.parquet"

    full = _load_meta_parquet_cached(path)
    if full.empty:
        raise SystemExit(f"No cached data at {path} -- set DATA_ROOT to a real allotmint-data checkout.")
    print(f"full frame rows: {len(full)}, dtype: {full['Date'].dtype}")

    end = full["Date"].max().date()
    start = end - datetime.timedelta(days=90)

    t0 = time.perf_counter()
    for _ in range(N_CALLS):
        sliced = apply_date_range(full, start, end)
    t_apply = time.perf_counter() - t0
    print(f"apply_date_range x{N_CALLS}: {t_apply:.4f}s ({len(sliced)} rows/slice)")

    t0 = time.perf_counter()
    for _ in range(N_CALLS):
        _ensure_schema(sliced.copy())
    t_ensure = time.perf_counter() - t0
    print(f"_ensure_schema on pre-sliced frame x{N_CALLS}: {t_ensure:.4f}s")

    t0 = time.perf_counter()
    for _ in range(N_CALLS):
        _ensure_schema(apply_date_range(full, start, end))
    t_combined = time.perf_counter() - t0
    print(f"apply_date_range + _ensure_schema combined x{N_CALLS}: {t_combined:.4f}s")


def run_e2e(owner: str) -> None:
    # Imported lazily: these pull in the full FastAPI app graph, which
    # run_micro doesn't need.
    from backend.common.portfolio import build_owner_portfolio
    from backend.common.portfolio_utils import aggregate_by_sector

    def build_and_aggregate() -> None:
        with cache_only():
            portfolio = build_owner_portfolio(owner)
            aggregate_by_sector(portfolio)

    # Warm-up pass: primes the per-ticker warm parquet cache (#8113), then
    # clear the per-(ticker,range) LRUs so the profiled pass reproduces
    # "shared warm cache, but this specific window hasn't been requested
    # before" -- the exact scenario #8127/#8131/#8137 all target.
    build_and_aggregate()
    _memoized_range_cached.cache_clear()
    _load_meta_timeseries_cached.cache_clear()

    profiler = cProfile.Profile()
    profiler.enable()
    build_and_aggregate()
    profiler.disable()

    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    print(f"TOTAL cumulative time for {owner}: {stats.total_tt:.4f}s")
    stats.print_stats(15)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "micro"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if mode == "e2e":
        run_e2e(arg or "steve")
    elif mode == "micro":
        run_micro(arg or "VOD_L")
    else:
        raise SystemExit(f"Unknown mode {mode!r}; expected 'micro' or 'e2e'.")


if __name__ == "__main__":
    main()
