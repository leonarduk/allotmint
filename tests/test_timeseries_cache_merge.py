import importlib
import sys
import warnings
from datetime import datetime, timedelta

import pandas as pd
from pandas.api.types import is_integer_dtype
from pandas.testing import assert_frame_equal


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def _seed_existing_parquet(
    cache, cache_path: str, days: int, *, include_window_end: bool = False
) -> pd.DataFrame:
    """Populate ``cache_path`` with deterministic sample data and return expected slice."""

    base_today = datetime.today().date()
    cutoff, window_end = cache._weekday_range(base_today - timedelta(days=1), days)

    start = cutoff - timedelta(days=2)
    end = window_end if include_window_end else max(cutoff, window_end - timedelta(days=1))
    dates = pd.date_range(start=start, end=end, freq="D")
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": [float(i) for i in range(len(dates))],
            "High": [float(i) + 1 for i in range(len(dates))],
            "Low": [float(i) - 1 for i in range(len(dates))],
            "Close": [float(i) + 0.5 for i in range(len(dates))],
            "Volume": [100 + i for i in range(len(dates))],
            "Ticker": ["ABC"] * len(dates),
            "Source": ["SRC"] * len(dates),
        }
    )
    cache._save_parquet(frame, cache_path)

    existing = cache._load_parquet(cache_path)
    mask = existing["Date"].dt.date >= cutoff
    return cache._ensure_schema(existing.loc[mask].reset_index(drop=True))


def test_merge_skips_empty_frames(monkeypatch, tmp_path):
    """Ensure merging works when existing cache is empty."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    def fetch_func(**_kwargs):
        today = datetime.today().date()
        data_date = today - timedelta(days=1)
        return pd.DataFrame(
            {
                "Date": [pd.Timestamp(data_date)],
                "Open": [1.0],
                "High": [2.0],
                "Low": [0.5],
                "Close": [1.5],
                "Volume": [100],
                "Ticker": ["ABC"],
                "Source": ["SRC"],
            }
        )

    cache_path = cache._cache_path("foo.parquet")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            "DataFrame concatenation with empty or all-NA entries is deprecated",
        )
        result = cache._rolling_cache(
            fetch_func,
            cache_path,
            {},
            days=2,
            ticker="ABC",
            exchange="L",
        )

    assert is_integer_dtype(result["Volume"])
    assert result["Volume"].iloc[0] == 100



def test_ensure_schema_missing_date(caplog):
    """Missing Date column should return empty frame with schema and log warning."""
    cache = import_cache()
    df = pd.DataFrame({"Open": [1.23], "Ticker": ["ABC"]})

    with caplog.at_level("WARNING", logger="timeseries_cache"):
        result = cache._ensure_schema(df)

    assert result.empty
    assert list(result.columns) == cache.EXPECTED_COLS
    assert "Timeseries missing 'Date' column" in caplog.text

def test_rolling_cache_serves_cached_slice_on_fetch_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache, "_FAILED_FETCH_COUNT", 0, raising=False)

    cache_path = cache._cache_path("foo.parquet")
    expected = _seed_existing_parquet(cache, cache_path, days=5)

    def failing_fetch(**_kwargs):
        raise RuntimeError("network boom")

    result = cache._rolling_cache(
        failing_fetch,
        cache_path,
        {},
        days=5,
        ticker="ABC",
        exchange="L",
    )

    assert_frame_equal(result, expected)
    assert cache._FAILED_FETCH_COUNT == 1


def test_rolling_cache_serves_cached_slice_on_empty_fetch(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache, "_FAILED_FETCH_COUNT", 0, raising=False)

    cache_path = cache._cache_path("foo.parquet")
    expected = _seed_existing_parquet(cache, cache_path, days=3)

    def empty_fetch(**_kwargs):
        return pd.DataFrame()

    result = cache._rolling_cache(
        empty_fetch,
        cache_path,
        {},
        days=3,
        ticker="ABC",
        exchange="L",
    )

    assert_frame_equal(result, expected)
    assert cache._FAILED_FETCH_COUNT == 0
