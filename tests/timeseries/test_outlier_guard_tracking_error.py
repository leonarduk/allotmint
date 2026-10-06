"""End-to-end: the zero-volume spike guard brings tracking error back to a
plausible range (#7816 AC #1).

The benchmark goes through the real ``load_meta_timeseries`` (so the guard in
``backend.timeseries.cache`` applies) with only the parquet/LRU layer stubbed;
``compute_tracking_error`` then runs unmodified. Data is synthetic but shaped
like the issue's VWRL.L parquet: Stooq closes around 120 with a handful of
zero-volume Yahoo rows at ~161 spliced in.
"""

import numpy as np
import pandas as pd
import pytest

from backend.common import portfolio_utils
from backend.timeseries import cache
from backend.timeseries.outlier_guard import drop_zero_volume_spikes

N_DAYS = 260
DAILY_ACTIVE_STD = 0.003  # ~4.8% annualised true tracking error
SPIKE_ROWS = (40, 95, 150, 151 + 50, 230)  # isolated, never adjacent


def _synthetic_data() -> tuple[pd.Series, pd.DataFrame]:
    rng = np.random.default_rng(7816)
    dates = pd.bdate_range("2025-01-02", periods=N_DAYS)
    bench_ret = rng.normal(0.0003, 0.009, N_DAYS)
    bench = 120.0 * np.cumprod(1 + bench_ret)
    port = 10_000.0 * np.cumprod(1 + bench_ret + rng.normal(0.0, DAILY_ACTIVE_STD, N_DAYS))

    closes = bench.copy()
    volumes = rng.integers(40_000, 150_000, N_DAYS).astype(float)
    sources = np.array(["Stooq"] * N_DAYS, dtype=object)
    for row in SPIKE_ROWS:  # the issue's bad rows: ~+34%, zero volume, Yahoo
        closes[row] = bench[row] * 1.345
        volumes[row] = 0
        sources[row] = "Yahoo"

    portfolio = pd.Series(port, index=dates.date)
    benchmark = pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": volumes,
            "Ticker": "VWRL.L",
            "Source": sources,
        }
    )
    return portfolio, benchmark


@pytest.fixture
def stub_sources(monkeypatch: pytest.MonkeyPatch):
    portfolio, benchmark = _synthetic_data()

    monkeypatch.setattr(
        portfolio_utils,
        "_portfolio_return_series",
        lambda name, days, *, group=False, pricing_date=None, **_: (portfolio, {"portfolio_return_basis": "price"}),
    )
    # Stub only the stored-data layer; load_meta_timeseries itself is real.
    monkeypatch.setattr(cache, "_load_meta_timeseries_cached", lambda *a, **k: benchmark)
    monkeypatch.setattr(cache, "_invalidate_meta_caches_if_stale", lambda *a, **k: None)
    monkeypatch.setattr(cache, "OFFLINE_MODE", cache.config.offline_mode)
    assert portfolio_utils.load_meta_timeseries is cache.load_meta_timeseries
    return benchmark


def test_tracking_error_is_plausible_with_guard(stub_sources) -> None:
    value = portfolio_utils.compute_tracking_error("alice", "VWRL.L", days=365)

    # Single-digit percent, as a decimal, close to the true ~4.8%.
    assert value is not None
    assert 0.02 < value < 0.10
    assert len(stub_sources) == N_DAYS  # stored/cached frame untouched


def test_tracking_error_without_guard_is_implausible(stub_sources, monkeypatch) -> None:
    guarded = portfolio_utils.compute_tracking_error("alice", "VWRL.L", days=365)

    monkeypatch.setattr(cache, "drop_zero_volume_spikes", lambda df, **_: df)
    unguarded = portfolio_utils.compute_tracking_error("alice", "VWRL.L", days=365)

    # The spliced rows alone push tracking error far beyond anything plausible
    # for a portfolio benchmarked against a global equity ETF.
    assert unguarded > 0.50
    assert unguarded > 10 * guarded


def test_guard_drops_exactly_the_spliced_rows(stub_sources) -> None:
    out = drop_zero_volume_spikes(stub_sources, ticker="VWRL", exchange="L")
    dropped = sorted(set(stub_sources.index) - set(out.index))
    assert dropped == sorted(SPIKE_ROWS)
