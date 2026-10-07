"""Profile the custom-query path (``backend/routes/query.py::_query_rows``) for #3424.

Runs one all-owners query over the last ten years with every metric
(``market_value_gbp``, ``gain_gbp``, ``var``, ``meta``) against whatever
``DATA_ROOT`` points at, and reports cold/warm wall time, both inside
``cache_only()`` and on the route's current live path, plus how many live
price fetches the live path would have made.

The network is never touched: ``fetch_meta_timeseries`` is replaced by a stub
that counts calls and returns nothing, parquet writes are disabled and the
background refresh queue is not fed. Point ``DATA_ROOT`` at a *copy* of
``allotmint-data`` anyway, since a run reads every cached parquet it prices.

Usage::

    DATA_ROOT=/path/to/copy/of/allotmint-data python -m scripts.profile_custom_query [--profile]

``--profile`` also prints the top cProfile entries by internal time for each run.
"""

from __future__ import annotations

import collections
import cProfile
import io
import pstats
import sys
import time
from contextlib import nullcontext
from datetime import date, timedelta

import backend.timeseries.cache as ts_cache
from backend.common import holding_utils
from backend.routes import query as query_module

_LIVE_FETCHES: collections.Counter = collections.Counter()
_TEN_YEARS = timedelta(days=3653)


def _count_live_fetch(ticker: str | None = None, exchange: str | None = None, **_kwargs):
    _LIVE_FETCHES[f"{ticker}.{exchange}"] += 1
    return ts_cache._empty_ts()


def _isolate_from_network() -> None:
    ts_cache.fetch_meta_timeseries = _count_live_fetch
    ts_cache._save_parquet = lambda *_a, **_k: None
    ts_cache._queue_if_stale = lambda *_a, **_k: None


def _reset_caches() -> None:
    ts_cache._memoized_range_cached.cache_clear()
    ts_cache._load_meta_timeseries_cached.cache_clear()
    ts_cache._load_meta_parquet_cached.cache_clear()
    holding_utils._unscaled_price_cache.clear()
    _LIVE_FETCHES.clear()


def _timed_run(q: query_module.CustomQuery, cache_only: bool, prof: cProfile.Profile | None) -> tuple[float, int]:
    started = time.perf_counter()
    with ts_cache.cache_only() if cache_only else nullcontext():
        if prof is not None:
            prof.enable()
        rows = query_module._query_rows(q)
        if prof is not None:
            prof.disable()
    return time.perf_counter() - started, len(rows)


def _profile(label: str, cache_only: bool, with_profile: bool) -> None:
    metric = query_module.Metric
    today = date.today()
    q = query_module.CustomQuery(
        start=today - _TEN_YEARS,
        end=today,
        metrics=[metric.MARKET_VALUE_GBP, metric.GAIN_GBP, metric.VAR, metric.META],
    )
    _reset_caches()
    prof = cProfile.Profile() if with_profile else None
    cold, n_rows = _timed_run(q, cache_only, prof)
    fetches, fetched_tickers = sum(_LIVE_FETCHES.values()), len(_LIVE_FETCHES)
    warm, _ = _timed_run(q, cache_only, None)
    print(
        f"{label}: rows={n_rows} cold={cold:.2f}s warm={warm:.2f}s "
        f"live fetches={fetches} over {fetched_tickers} tickers"
    )
    if prof is not None:
        out = io.StringIO()
        pstats.Stats(prof, stream=out).sort_stats("tottime").print_stats(15)
        print(out.getvalue())


def main() -> None:
    _isolate_from_network()
    with_profile = "--profile" in sys.argv[1:]
    _profile("live path (route today)", cache_only=False, with_profile=with_profile)
    _profile("cache_only()", cache_only=True, with_profile=with_profile)


if __name__ == "__main__":
    main()
