# Decision: don't parallelise the custom-query path (#3424)

Status: **Accepted**. This resolves the profiling spike in
[#3424](https://github.com/leonarduk/allotmint/issues/3424).

**Decision:** do not add `ProcessPoolExecutor`, `ThreadPoolExecutor`,
`pandarallel` or `joblib` to `backend/routes/query.py`. The path is CPU-bound,
and most of that CPU goes on repeated work. On a Lambda with less than one vCPU,
parallelism cannot fix that, but removing the repeated work can. One such fix
ships with this spike. The rest are listed under follow-ups below.

## What was measured

- **Path:** `_query_rows` (behind `POST/GET /custom-query/run`) with every metric
  (`market_value_gbp`, `gain_gbp`, `var`, `meta`), all owners, and a 10-year
  range ending today.
- **Data:** a copy of `allotmint-data`: 5 owners, 104 (owner, ticker) rows,
  76 distinct tickers, and 160 cached parquets totalling 444k rows. This is the
  real multi-position, multi-year shape, not a synthetic frame.
- **Harness:** `scripts/profile_custom_query.py`. It stubs out the network, so
  live fetches are counted rather than made. Run it like this:
  `DATA_ROOT=<copy of allotmint-data> python -m scripts.profile_custom_query --profile`
- **Machine:** a Windows dev box running Python 3.13 and pandas 3. Wall times
  are noisy, so treat them as ratios rather than absolute numbers.

### Wall time (not profiled)

| Run | Cold | Warm |
| --- | --- | --- |
| Inside `cache_only()` | 4.4–7.1 s | 1.7–4.0 s |
| Live path, as the route runs today | 3.5–7.9 s | 1.7–3.2 s |

On a cold run the live path also attempted **52 live price fetches across 32
tickers**. In production each one is a Yahoo or Stooq round trip. Here they were
stubbed to return nothing, which is why the live path can look *faster* than
`cache_only()` in this table.

### Where the time goes (cProfile, cold `cache_only()` run, 12.9 s under the profiler)

| Function | Calls | Cumulative time |
| --- | --- | --- |
| `cache._guarded_range` | 249 | 6.9 s |
| ↳ `outlier_guard.drop_zero_volume_spikes` | 249 | 5.0 s |
| ↳↳ `outlier_guard._normalised_sources` (a per-row Python loop) | 249 | **3.6 s** |
| ↳ `cache._without_pre_epoch_rows` (`to_datetime` over the full history) | 249 | 1.1 s |
| VaR: `compute_var_with_basis` → `total_return_series` | 76 | 3.4 s |
| `pandas.read_parquet` | 155 | 1.0 s |
| `load_transactions` + `list_portfolios` | 5 | 0.04 s |

What the profile shows:

1. **The path is CPU-bound.** Parquet reads take about 1 s of 12.9 s on local
   disk, and portfolio/transaction loading is negligible. The rest is pandas and
   Python-level loops, all holding the GIL.
2. **Most of the CPU goes on repeated work.** There are 249 range-cache fills
   for 76 tickers. A fill happens for each distinct `(ticker, start, end)` key:
   the start and end prices in `_gbp_price`, each walk-back day, and the window
   of each `load_meta_timeseries_range` offset all count separately. Every fill
   re-runs the spike guard and the pre-epoch filter over the ticker's **whole**
   history before slicing a few rows out of it.
3. **VaR is never memoised.** It is recomputed on every request, so it makes up
   most of the warm cost.
4. **The route still fetches live.** Unlike the other page routes
   (`backend/routes/portfolio.py`, `movers.py`, `fx.py`), `query.py` never
   enters `cache_only()`. A cold request can therefore make network calls inline.
   That conflicts with the "page requests never fetch" rule (#7898, #8028).

## Why not parallelise

- **No CPU to spread the work across.** `BackendLambda` runs at
  `memory_size=1024` (`cdk/stacks/backend_lambda_stack.py`). Lambda allocates
  CPU in proportion to memory and reaches one full vCPU at 1,769 MB, so this
  function gets roughly 0.6 vCPU. A process pool has no second core to use.
- **`ProcessPoolExecutor`, `joblib` and `pandarallel` cost more than they save.**
  Lambda needs the `spawn` start method, and each spawned worker re-imports
  pandas and `backend.*`, which takes seconds. Each per-ticker DataFrame would
  also be pickled in and out. That cost is about the same as the whole query,
  with no extra core to recover it. `pandarallel` also assumes `fork`.
- **`ThreadPoolExecutor` does nothing for the work being done.** The hot loops
  hold the GIL. Threads would only help the I/O part: live fetches, plus S3
  parquet reads in AWS, which were not measured here. The fix for live fetches
  is to stop making them (follow-up 1), not to make them concurrently.
- **If S3 read latency later turns out to matter** in CloudWatch, the
  sanctioned pattern already exists: `ThreadPoolExecutor` together with
  `cache.map_in_caller_context`, as used in `backend/common/prices.py` and
  `backend/common/instrument_api.py`. Use it to prefetch per-ticker parquets.
  Measure first.

## What shipped with this spike

`_normalised_sources` (`backend/timeseries/outlier_guard.py`) now normalises
each distinct `Source` label once, using `pd.factorize`, instead of once per
row. A parquet holds 2–3 distinct labels over thousands of rows.

- The output is identical on all 160 real parquets, and new tests pin it
  against the old per-row rule for object, `string` and `str` dtypes and for
  `None`, `NaN` and `pd.NA`.
- On those parquets the function is 18× faster: 358 ms → 19 ms.
- A cold custom query got about 15% faster. Over 6 interleaved runs the median
  went from 5.23 s to 4.46 s.

The guard runs on every meta timeseries read, live or cache-only, so every page
route that reads prices benefits, not only `/custom-query`.

## Follow-ups (recommended, not done here)

Listed in order of expected payoff. Each changes behaviour or caching, so each
needs its own issue.

1. **Run `_query_rows` inside `cache_only()`.** This takes live fetches out of
   the request path, which matches every other page route. Behaviour change: an
   uncached ticker gets its last cached close, or no value, instead of a live
   fetch, and is queued for background refresh.
2. **Run the guard once per parquet, not once per range key.** Memoise
   `drop_zero_volume_spikes(_without_pre_epoch_rows(existing))` per cache path
   and invalidate it with the other meta LRUs. Each range fill then only slices
   the cleaned frame. This removes most of the remaining `_guarded_range` cost.
   The guard is neighbour-dependent, so it still has to see the full history
   rather than the slice.
3. **Memoise VaR per `(ticker, start, end)`** inside `cache_only()`, the same
   way #8211 memoised single-day prices. Most of the warm cost goes away.
