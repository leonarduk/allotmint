import importlib
import sys
import warnings
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from pandas.api.types import is_integer_dtype
from pandas.testing import assert_frame_equal


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def _seed_existing_parquet(cache, cache_path: str, days: int, *, include_window_end: bool = False) -> pd.DataFrame:
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


@pytest.mark.parametrize(
    "date_input,input_id",
    [
        (pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[ns]"), "ns"),
        (pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[ms]"), "ms"),
        (pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[s]"), "s"),
        ([date(2024, 1, 1), date(2024, 1, 2)], "date_objects"),
        (pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC"), "tz_aware_utc"),
        (
            pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("US/Eastern"),
            "tz_aware_non_utc",
        ),
    ],
    ids=["ns", "ms", "s", "date_objects", "tz_aware_utc", "tz_aware_non_utc"],
)
def test_ensure_schema_normalises_date_to_ms(date_input, input_id):
    """_ensure_schema must always return datetime64[ms] for the Date column.

    Regression test for the pandas 2→3 datetime resolution change: pandas 3.x
    infers datetime64[s] from Python date objects while 2.x infers datetime64[ns].
    Regardless of the input resolution, _ensure_schema must pin Date to
    datetime64[ms] so that code paths involving .dt.date round-trips compare
    equal to paths reading directly from pyarrow parquet files (which default
    to ms precision).
    """
    cache = import_cache()
    df = pd.DataFrame(
        {
            "Date": date_input,
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [100, 200],
            "Ticker": ["ABC", "ABC"],
            "Source": ["SRC", "SRC"],
        }
    )
    result = cache._ensure_schema(df)
    assert (
        result["Date"].dtype == "datetime64[ms]"
    ), f"input_id={input_id}: expected datetime64[ms], got {result['Date'].dtype}"


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


def _single_row(cache, day: date) -> pd.DataFrame:
    return cache._ensure_schema(
        pd.DataFrame(
            {
                "Date": [pd.Timestamp(day)],
                "Open": [9.0],
                "High": [9.0],
                "Low": [9.0],
                "Close": [9.0],
                "Volume": [1],
                "Ticker": ["ABC"],
                "Source": ["Yahoo"],
            }
        )
    )


def test_rolling_cache_skips_save_when_fetch_adds_no_new_dates(monkeypatch, tmp_path):
    """A fetch that only returns already-cached dates must not rewrite the file (#7877).

    Rewriting bumps the mtime, which clears every ticker's meta LRU entries and
    re-triggers the same fetch on the next lookup.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    cache_path = cache._cache_path("foo.parquet")
    expected = _seed_existing_parquet(cache, cache_path, days=5)
    last_cached = expected["Date"].dt.date.max()

    saves = []
    monkeypatch.setattr(cache, "_save_parquet", lambda df, path: saves.append(path))

    result = cache._rolling_cache(
        lambda **_kwargs: _single_row(cache, last_cached),
        cache_path,
        {},
        days=5,
        ticker="ABC",
        exchange="L",
    )

    assert saves == []
    assert_frame_equal(result, expected)


def test_rolling_cache_saves_when_fetch_adds_new_date(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    cache_path = cache._cache_path("foo.parquet")
    expected = _seed_existing_parquet(cache, cache_path, days=5)
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 5)
    assert window_end not in set(expected["Date"].dt.date)

    result = cache._rolling_cache(
        lambda **_kwargs: _single_row(cache, window_end),
        cache_path,
        {},
        days=5,
        ticker="ABC",
        exchange="L",
    )

    assert window_end in set(result["Date"].dt.date)
    assert window_end in set(cache._load_parquet(cache_path)["Date"].dt.date)


def test_rolling_cache_saves_on_first_fetch_for_ticker(monkeypatch, tmp_path):
    """With no cached file yet (``existing.empty``), the first fetch must be saved."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    cache_path = cache._cache_path("foo.parquet")
    assert cache._load_parquet(cache_path).empty
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 5)

    result = cache._rolling_cache(
        lambda **_kwargs: _single_row(cache, window_end),
        cache_path,
        {},
        days=5,
        ticker="ABC",
        exchange="L",
    )

    assert list(result["Date"].dt.date) == [window_end]
    assert list(cache._load_parquet(cache_path)["Date"].dt.date) == [window_end]


@pytest.mark.parametrize("adds_new_date", [False, True], ids=["no_new_dates", "new_date"])
def test_s3_save_skip_keeps_meta_lru_entries(monkeypatch, adds_new_date):
    """With an s3:// cache, a skipped save leaves LastModified unchanged, so the meta LRUs survive (#7877).

    S3 is stubbed with an in-memory store: ``_load_parquet``/``_save_parquet``
    read and write it, and ``head_object`` reports its LastModified. No AWS
    calls are made.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 5)
    seeded = cache._ensure_schema(
        pd.concat(
            [_single_row(cache, d.date()) for d in pd.date_range(cutoff - timedelta(days=2), cutoff)],
            ignore_index=True,
        )
    )
    cache_path = cache.meta_timeseries_cache_path("ABC", "L")
    store = {cache_path: (seeded, datetime(2026, 1, 1))}
    saves = []

    def fake_save(df, path):
        saves.append(path)
        store[path] = (cache._ensure_schema(df), store[path][1] + timedelta(hours=1))

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            assert (Bucket, Key) == ("bucket", "timeseries/meta/ABC_L.parquet")
            return {"LastModified": store[cache_path][1]}

    monkeypatch.setattr(cache, "_load_parquet", lambda path: store[path][0].copy())
    monkeypatch.setattr(cache, "_save_parquet", fake_save)
    monkeypatch.setattr(cache, "_s3_client", lambda: FakeS3Client())
    fetch_day = window_end if adds_new_date else cutoff
    monkeypatch.setattr(cache, "fetch_meta_timeseries", lambda **_kwargs: _single_row(cache, fetch_day))

    cache._invalidate_meta_caches_if_stale("ABC", "L")
    mtime_before = cache._s3_object_mtime(cache_path)
    cache._load_meta_timeseries_cached("ABC", "L", 5)
    assert cache._load_meta_timeseries_cached.cache_info().currsize == 1

    # Drop the 30s mtime memo so the next check issues a fresh HeadObject.
    cache.invalidate_s3_cache_metadata(cache_path)
    mtime_after = cache._s3_object_mtime(cache_path)
    cache._invalidate_meta_caches_if_stale("ABC", "L")

    if adds_new_date:
        assert saves == [cache_path]
        assert mtime_after != mtime_before
        assert cache._load_meta_timeseries_cached.cache_info().currsize == 0
    else:
        assert saves == []
        assert mtime_after == mtime_before
        assert cache._load_meta_timeseries_cached.cache_info().currsize == 1
