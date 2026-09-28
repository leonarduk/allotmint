"""Reproduce the #8137 _ensure_schema microbenchmark against real cached data.

Requires the ``allotmint-data`` sibling checkout (set ``DATA_ROOT``/
``config.yaml``'s ``paths.data_root`` to point at it) with at least one
warm ``timeseries/meta/<TICKER>_<EXCHANGE>.parquet`` file present -- this
does not fabricate data, since the whole point is to measure against a
realistic per-ticker history shape (row count, dtype) rather than a
synthetic frame.

Usage::

    DATA_ROOT=../allotmint-data python -m scripts.profile_ensure_schema [TICKER_EXCHANGE]

``TICKER_EXCHANGE`` defaults to ``VOD_L`` (an arbitrary real ticker from the
`allotmint-data` fixture set used throughout #8105/#8113/#8127/#8131/#8137).
"""

from __future__ import annotations

import datetime
import sys
import time

from backend.timeseries.cache import _CACHE_BASE, _ensure_schema, _load_meta_parquet_cached
from backend.utils.timeseries_helpers import apply_date_range

# Matches #8127/#8131's measured per-(ticker, date-range) call count for the
# worst-case owner ("steve") against the allotmint-data fixture set.
N_CALLS = 1453


def main() -> None:
    ticker_exchange = sys.argv[1] if len(sys.argv) > 1 else "VOD_L"
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


if __name__ == "__main__":
    main()
