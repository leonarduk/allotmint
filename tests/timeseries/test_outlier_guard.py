"""Tests for the zero-volume price spike guard (#7816)."""

import logging

import numpy as np
import pandas as pd
import pytest

from backend.timeseries import cache
from backend.timeseries.outlier_guard import drop_zero_volume_spikes


def _frame(closes, volumes, sources=None, start="2025-09-29"):
    """Build a frame; by default zero-volume rows are "Yahoo", others "Stooq"."""
    dates = pd.bdate_range(start, periods=len(closes))
    if sources is None:
        sources = ["Yahoo" if v == 0 else "Stooq" for v in volumes]
    return pd.DataFrame({"Date": dates, "Close": closes, "Volume": volumes, "Source": sources})


# The VWRL.L rows quoted on #7816: Stooq closes ~120 interleaved with
# zero-volume Yahoo rows at ~161.
VWRL_CLOSES = [119.25, 161.56, 120.52, 120.90, 162.78, 120.73]
VWRL_VOLUMES = [100931, 0, 136232, 98081, 0, 63010]


def test_drops_isolated_zero_volume_spikes_from_issue_example(caplog):
    df = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    with caplog.at_level(logging.WARNING, logger="backend.timeseries.outlier_guard"):
        out = drop_zero_volume_spikes(df, ticker="VWRL", exchange="L")
    assert out["Close"].tolist() == [119.25, 120.52, 120.90, 120.73]
    assert "2 zero-volume price spike(s) for VWRL.L" in caplog.text
    # Daily returns are now all small.
    assert out["Close"].pct_change().abs().max() < 0.02


def test_benchmark_return_volatility_becomes_plausible():
    df = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    raw_returns = df["Close"].pct_change().dropna()
    guarded_returns = drop_zero_volume_spikes(df, ticker="VWRL", exchange="L")["Close"].pct_change().dropna()
    assert raw_returns.std() * np.sqrt(252) > 4  # >400% annualised from the spikes
    assert guarded_returns.std() * np.sqrt(252) < 0.2


def test_does_not_mutate_input_and_returns_same_object_when_clean():
    df = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    snapshot = df.copy()
    drop_zero_volume_spikes(df, ticker="VWRL", exchange="L")
    pd.testing.assert_frame_equal(df, snapshot)

    clean = _frame([100.0, 101.0, 102.0, 101.5], [10, 0, 12, 13])
    assert drop_zero_volume_spikes(clean, ticker="X", exchange="L") is clean


def test_keeps_spike_with_volume():
    df = _frame([100.0, 140.0, 101.0], [10, 500, 12])
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    assert len(out) == 3


def test_keeps_zero_volume_level_shift():
    # Moves away from the previous close but stays near the next: a real move.
    df = _frame([100.0, 130.0, 131.0], [10, 0, 12])
    assert len(drop_zero_volume_spikes(df, ticker="X", exchange="L")) == 3


def test_keeps_when_neighbours_disagree():
    df = _frame([100.0, 150.0, 120.0], [10, 0, 12])
    assert len(drop_zero_volume_spikes(df, ticker="X", exchange="L")) == 3


def test_keeps_edge_rows_and_adjacent_spikes():
    edge = _frame([160.0, 120.0, 121.0, 160.0], [0, 10, 11, 0])
    assert len(drop_zero_volume_spikes(edge, ticker="X", exchange="L")) == 4

    adjacent = _frame([120.0, 160.0, 161.0, 121.0], [10, 0, 0, 11])
    assert len(drop_zero_volume_spikes(adjacent, ticker="X", exchange="L")) == 4


def test_missing_volume_column_counts_as_no_volume():
    df = _frame([120.0, 160.0, 121.0], [10, 0, 10]).drop(columns="Volume")
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    assert out["Close"].tolist() == [120.0, 121.0]


def test_keeps_same_source_zero_volume_v_shaped_move():
    # A genuine zero-volume round trip from one provider (halted / illiquid
    # line) passes every price test but must not be dropped.
    df = _frame([100.0, 80.0, 100.0, 101.0], [10, 0, 0, 11], sources=["Stooq"] * 4)
    assert drop_zero_volume_spikes(df, ticker="X", exchange="L") is df


def test_keeps_spike_when_source_matches_either_neighbour():
    left = _frame([120.0, 160.0, 121.0], [10, 0, 10], sources=["Yahoo", "Yahoo", "Stooq"])
    assert len(drop_zero_volume_spikes(left, ticker="X", exchange="L")) == 3
    right = _frame([120.0, 160.0, 121.0], [10, 0, 10], sources=["Stooq", "Yahoo", "Yahoo"])
    assert len(drop_zero_volume_spikes(right, ticker="X", exchange="L")) == 3


def test_keeps_rows_when_source_missing_or_blank():
    no_column = _frame(VWRL_CLOSES, VWRL_VOLUMES).drop(columns="Source")
    assert drop_zero_volume_spikes(no_column, ticker="VWRL", exchange="L") is no_column

    blank = _frame([120.0, 160.0, 121.0], [10, 0, 10], sources=["Stooq", None, "Stooq"])
    assert len(drop_zero_volume_spikes(blank, ticker="X", exchange="L")) == 3
    blank_neighbour = _frame([120.0, 160.0, 121.0], [10, 0, 10], sources=["", "Yahoo", "Stooq"])
    assert len(drop_zero_volume_spikes(blank_neighbour, ticker="X", exchange="L")) == 3


def test_source_comparison_ignores_case_and_whitespace():
    df = _frame([120.0, 160.0, 121.0], [10, 0, 10], sources=["Stooq", "yahoo", " stooq "])
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    assert out["Close"].tolist() == [120.0, 121.0]


def test_handles_unsorted_dates_and_preserves_attrs():
    df = _frame(VWRL_CLOSES, VWRL_VOLUMES).iloc[::-1]
    df.attrs["source"] = "meta"
    out = drop_zero_volume_spikes(df, ticker="VWRL", exchange="L")
    # Original (reversed) row order is preserved; only the spikes are removed.
    assert out["Close"].tolist() == [120.73, 120.90, 120.52, 119.25]
    assert out.attrs == {"source": "meta"}


def test_ignores_invalid_closes_when_choosing_neighbours():
    df = _frame([120.0, np.nan, 160.0, 0.0, 121.0], [10, 5, 0, 5, 11])
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    # The 160 row is compared against 120 and 121 (the nearest valid closes).
    assert out["Close"].tolist() == pytest.approx([120.0, np.nan, 0.0, 121.0], nan_ok=True)


def test_short_or_empty_frames_returned_unchanged():
    empty = pd.DataFrame()
    assert drop_zero_volume_spikes(empty, ticker="X", exchange="L") is empty
    two = _frame([120.0, 160.0], [10, 0])
    assert drop_zero_volume_spikes(two, ticker="X", exchange="L") is two


def test_load_meta_timeseries_applies_guard(monkeypatch):
    raw = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    monkeypatch.setattr(cache, "_load_meta_timeseries_cached", lambda *a, **k: raw)
    monkeypatch.setattr(cache, "_invalidate_meta_caches_if_stale", lambda *a, **k: None)
    monkeypatch.setattr(cache, "OFFLINE_MODE", cache.config.offline_mode)
    out = cache.load_meta_timeseries("VWRL", "L", 365)
    assert out["Close"].tolist() == [119.25, 120.52, 120.90, 120.73]
    assert len(raw) == len(VWRL_CLOSES)  # cached frame untouched
    again = cache.load_meta_timeseries("VWRL", "L", 365)  # repeat cache hit
    pd.testing.assert_frame_equal(again, out)
    assert len(raw) == len(VWRL_CLOSES)


def _spike_log_count(caplog) -> int:
    return sum("price spike(s)" in r.getMessage() for r in caplog.records)


@pytest.fixture
def fresh_range_cache():
    cache._memoized_range_cached.cache_clear()
    yield
    cache._memoized_range_cached.cache_clear()


def test_memoized_range_cache_only_branch_guards_once(monkeypatch, caplog, fresh_range_cache):
    # The cache-only branch reads the parquet directly, so the guard runs
    # inside the LRU cache: applied once, logged once, not on every read.
    raw = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    monkeypatch.setattr(cache, "_load_meta_parquet_cached", lambda path: raw)
    monkeypatch.setattr(cache, "_queue_if_stale", lambda *a, **k: None)
    token = cache._CACHE_ONLY.set(True)
    try:
        with caplog.at_level(logging.WARNING, logger="backend.timeseries.outlier_guard"):
            first = cache._memoized_range("VWRL", "L", "2025-09-29", "2025-10-06")
            second = cache._memoized_range("VWRL", "L", "2025-09-29", "2025-10-06")
    finally:
        cache._CACHE_ONLY.reset(token)
    assert first["Close"].tolist() == [119.25, 120.52, 120.90, 120.73]
    pd.testing.assert_frame_equal(first, second)
    assert _spike_log_count(caplog) == 1
    assert len(raw) == len(VWRL_CLOSES)


def test_memoized_range_live_branch_guards_once(monkeypatch, caplog, fresh_range_cache):
    # The live branch is guarded by load_meta_timeseries; _memoized_range
    # must not run the guard a second time on top.
    raw = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.setattr(cache, "_invalidate_meta_caches_if_stale", lambda *a, **k: None)
    monkeypatch.setattr(cache, "_load_meta_timeseries_cached", lambda *a, **k: raw)
    with caplog.at_level(logging.WARNING, logger="backend.timeseries.outlier_guard"):
        out = cache._memoized_range("VWRL", "L", "2025-09-29", "2025-10-06")
    assert out["Close"].tolist() == [119.25, 120.52, 120.90, 120.73]
    assert _spike_log_count(caplog) == 1


def test_source_comparison_handles_pd_na_and_nan():
    sources = pd.array(["Stooq", pd.NA, "Stooq", "Stooq", "Yahoo", "Stooq"], dtype="string")
    df = _frame([120.0, 160.0, 121.0, 120.5, 161.0, 120.8], [10, 0, 10, 10, 0, 10], sources=sources)
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    # The pd.NA-sourced spike is kept (unknown provenance); the Yahoo one goes.
    assert out["Close"].tolist() == [120.0, 160.0, 121.0, 120.5, 120.8]

    obj = _frame([120.0, 160.0, 121.0], [10, 0, 10], sources=["Stooq", np.nan, "Stooq"])
    assert drop_zero_volume_spikes(obj, ticker="X", exchange="L") is obj


def test_no_false_positives_on_clean_interleaved_stooq_yahoo_series():
    # A year of realistic mixed-provenance data: Stooq rows trade volume,
    # Yahoo rows are zero-volume, but every row is on the same price level.
    rng = np.random.default_rng(7816)
    n = 260
    closes = 120.0 * np.cumprod(1 + rng.normal(0.0003, 0.009, n))
    is_yahoo = rng.random(n) < 0.4
    volumes = np.where(is_yahoo, 0, rng.integers(40_000, 150_000, n))
    sources = np.where(is_yahoo, "Yahoo", "Stooq")
    # Include a genuine zero-volume cross-source gap that does not revert.
    closes[150:] *= 0.82
    volumes[150], sources[150] = 0, "Yahoo"
    df = _frame(closes.tolist(), volumes.tolist(), sources=sources.tolist())

    assert drop_zero_volume_spikes(df, ticker="VWRL", exchange="L") is df


# The VHYL.L rows quoted on #9294: a flat, zero-volume Yahoo bar at 78.41
# between Yahoo bars at ~58. Same source throughout, so only the flat-bar
# test can catch it.
VHYL = pd.DataFrame(
    {
        "Date": pd.to_datetime(["2025-09-26", "2025-10-01", "2025-10-08"]),
        "Open": [57.92, 78.41, 58.67],
        "High": [58.44, 78.41, 58.76],
        "Low": [57.87, 78.41, 58.47],
        "Close": [58.01, 78.41, 58.69],
        "Volume": [77523, 0, 74571],
        "Source": ["Yahoo", "Yahoo", "Yahoo"],
    }
)


def test_drops_same_source_flat_zero_volume_spike_from_vhyl_example(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.timeseries.outlier_guard"):
        out = drop_zero_volume_spikes(VHYL, ticker="VHYL", exchange="L")
    assert out["Close"].tolist() == [58.01, 58.69]
    assert "1 zero-volume price spike(s) for VHYL.L" in caplog.text
    assert "2025-10-01=78.41" in caplog.text


def test_keeps_same_source_flat_zero_volume_bar_within_threshold():
    df = VHYL.copy()
    df.loc[1, ["Open", "High", "Low", "Close"]] = 62.0  # ~7% off: not a spike
    assert drop_zero_volume_spikes(df, ticker="VHYL", exchange="L") is df


def test_keeps_same_source_non_flat_zero_volume_spike():
    df = VHYL.copy()
    df.loc[1, "High"] = 79.10  # an intraday range: not a placeholder bar
    assert drop_zero_volume_spikes(df, ticker="VHYL", exchange="L") is df


def test_keeps_flat_spike_with_volume():
    df = VHYL.copy()
    df.loc[1, "Volume"] = 1200
    assert drop_zero_volume_spikes(df, ticker="VHYL", exchange="L") is df


def test_keeps_flat_bar_when_ohlc_missing_or_nan():
    no_open = VHYL.drop(columns="Open")
    assert drop_zero_volume_spikes(no_open, ticker="VHYL", exchange="L") is no_open
    nan_low = VHYL.copy()
    nan_low.loc[1, "Low"] = np.nan
    assert drop_zero_volume_spikes(nan_low, ticker="VHYL", exchange="L") is nan_low


def test_flat_spike_dropped_without_source_column(caplog):
    df = VHYL.drop(columns="Source")
    with caplog.at_level(logging.WARNING, logger="backend.timeseries.outlier_guard"):
        out = drop_zero_volume_spikes(df, ticker="VHYL", exchange="L")
    assert out["Close"].tolist() == [58.01, 58.69]
    # The drop is still logged when there is no Source column to report.
    assert "2025-10-01=78.41" in caplog.text


def test_keeps_flat_zero_volume_level_shift():
    # A flat untraded bar that the next row confirms is a real move, not a spike.
    df = VHYL.copy()
    df.loc[2, ["Open", "High", "Low", "Close"]] = [78.0, 79.2, 77.9, 78.9]
    assert drop_zero_volume_spikes(df, ticker="VHYL", exchange="L") is df


def test_flat_spike_at_edge_is_kept():
    edge = VHYL.iloc[:2].reset_index(drop=True)
    edge = pd.concat([VHYL.iloc[[0]], edge], ignore_index=True)
    edge.loc[0, "Date"] = pd.Timestamp("2025-09-25")
    # [58.01, 58.01, 78.41]: the flat bar is the last row, so it has one neighbour.
    assert drop_zero_volume_spikes(edge, ticker="VHYL", exchange="L") is edge


def test_flat_spike_at_start_is_kept():
    first = pd.concat([VHYL.iloc[[1]], VHYL.iloc[[0, 2]]], ignore_index=True)
    first.loc[0, "Date"] = pd.Timestamp("2025-09-25")
    # [78.41, 58.01, 58.69]: the flat bar is the first row, so it has one neighbour.
    assert drop_zero_volume_spikes(first, ticker="VHYL", exchange="L") is first
