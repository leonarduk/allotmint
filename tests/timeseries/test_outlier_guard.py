"""Tests for the zero-volume price spike guard (#7816)."""

import logging

import numpy as np
import pandas as pd

from backend.timeseries import cache
from backend.timeseries.outlier_guard import drop_zero_volume_spikes


def _frame(closes, volumes, start="2025-09-29"):
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Date": dates, "Close": closes, "Volume": volumes})


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


def test_tracking_error_inputs_become_plausible():
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
    df = _frame([120.0, 160.0, 121.0], [0, 0, 0]).drop(columns="Volume")
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    assert out["Close"].tolist() == [120.0, 121.0]


def test_handles_unsorted_dates_and_preserves_attrs():
    df = _frame(VWRL_CLOSES, VWRL_VOLUMES).iloc[::-1]
    df.attrs["source"] = "meta"
    out = drop_zero_volume_spikes(df, ticker="VWRL", exchange="L")
    assert sorted(out["Close"].tolist()) == sorted([119.25, 120.52, 120.90, 120.73])
    assert out.attrs == {"source": "meta"}


def test_ignores_invalid_closes_when_choosing_neighbours():
    df = _frame([120.0, np.nan, 160.0, 0.0, 121.0], [10, 5, 0, 5, 11])
    out = drop_zero_volume_spikes(df, ticker="X", exchange="L")
    assert len(out) == 4
    assert 160.0 not in out["Close"].tolist()


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


def test_memoized_range_applies_guard(monkeypatch):
    raw = _frame(VWRL_CLOSES, VWRL_VOLUMES)
    monkeypatch.setattr(cache, "_memoized_range_cached", lambda *a, **k: raw)
    out = cache._memoized_range("VWRL", "L", "2025-09-29", "2025-10-06")
    assert out["Close"].tolist() == [119.25, 120.52, 120.90, 120.73]
    assert len(raw) == len(VWRL_CLOSES)
