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
    """A fetch that only re-returns identical cached rows must not rewrite the file (#7877).

    Rewriting bumps the mtime, which clears every ticker's meta LRU entries and
    re-triggers the same fetch on the next lookup. (Before #7914 this fetched a
    *different* Close for the cached date; that is now a correction and is saved.)
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
        lambda **_kwargs: expected.loc[expected["Date"].dt.date == last_cached].copy(),
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


def _day_frame(cache, day: date, close: float, *, source: str = "SRC") -> pd.DataFrame:
    return cache._ensure_schema(
        pd.DataFrame(
            {
                "Date": [pd.Timestamp(day)],
                "Open": [close],
                "High": [close],
                "Low": [close],
                "Close": [close],
                "Volume": [100],
                "Ticker": ["ABC"],
                "Source": [source],
            }
        )
    )


@pytest.fixture(params=["local", "s3"])
def cache_store(request, monkeypatch, tmp_path):
    """Yield ``(cache, cache_path, saves)`` for a local-disk or an ``s3://`` cache base.

    The S3 variant keeps the parquet in memory by stubbing ``_load_parquet`` /
    ``_save_parquet``, so the merge/skip decision is exercised against an
    ``s3://`` path without network access.
    """
    saves: list[pd.DataFrame] = []
    if request.param == "local":
        monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
        cache = import_cache()
        real_save = cache._save_parquet

        def recording_save(df, path):
            saves.append(df.copy())
            real_save(df, path)

        monkeypatch.setattr(cache, "_save_parquet", recording_save)
    else:
        monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/ts")
        cache = import_cache()
        store: dict[str, pd.DataFrame] = {}

        def fake_save(df, path):
            saves.append(df.copy())
            store[path] = cache._ensure_schema(df.copy())

        monkeypatch.setattr(cache, "_save_parquet", fake_save)
        monkeypatch.setattr(cache, "_load_parquet", lambda path: store.get(path, cache._empty_ts()).copy())
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    cache_path = cache._cache_path("foo.parquet")
    if request.param == "s3":
        assert cache_path.startswith("s3://")
    return cache, cache_path, saves


def _seed_close_10(cache, cache_path, saves) -> date:
    """Cache Close=10 for the day before the window end (so the next call fetches)."""
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 5)
    day = window_end - timedelta(days=1)
    cache._save_parquet(_day_frame(cache, day, 10.0), cache_path)
    saves.clear()
    return day


def _run(cache, cache_path, fetched: pd.DataFrame) -> pd.DataFrame:
    return cache._rolling_cache(lambda **_kwargs: fetched, cache_path, {}, days=5, ticker="ABC", exchange="L")


def test_rolling_cache_persists_corrected_close_for_cached_date(cache_store):
    """Cached Close=10 for D, fetch returns Close=11 for D: the correction wins and is saved (#7914)."""
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)

    result = _run(cache, cache_path, _day_frame(cache, day, 11.0, source="Yahoo"))

    assert len(saves) == 1
    stored = cache._load_parquet(cache_path)
    assert list(stored["Date"].dt.date) == [day]
    assert stored["Close"].tolist() == [11.0]
    assert stored["Source"].tolist() == ["Yahoo"]
    assert result.loc[result["Date"].dt.date == day, "Close"].tolist() == [11.0]


def test_rolling_cache_identical_refetch_does_not_save(cache_store):
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)

    result = _run(cache, cache_path, _day_frame(cache, day, 10.0))

    assert saves == []
    assert result["Close"].tolist() == [10.0]


def test_rolling_cache_ignores_float_noise_and_source_only_changes(cache_store):
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)

    result = _run(cache, cache_path, _day_frame(cache, day, 10.0 * (1 + 1e-12), source="Stooq"))

    assert saves == []
    assert result["Close"].tolist() == [10.0]
    assert result["Source"].tolist() == ["SRC"]


def test_rolling_cache_fetched_row_without_close_does_not_overwrite(cache_store):
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)
    fetched = _day_frame(cache, day, 11.0)
    fetched["Close"] = float("nan")

    result = _run(cache, cache_path, fetched)

    assert saves == []
    assert result["Close"].tolist() == [10.0]


def test_rolling_cache_saves_correction_and_new_date_together(cache_store):
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)
    new_day = day + timedelta(days=1)
    fetched = pd.concat([_day_frame(cache, day, 11.0), _day_frame(cache, new_day, 12.0)], ignore_index=True)

    result = _run(cache, cache_path, fetched)

    assert len(saves) == 1
    assert dict(zip(result["Date"].dt.date, result["Close"])) == {day: 11.0, new_day: 12.0}
    stored = cache._load_parquet(cache_path)
    assert dict(zip(stored["Date"].dt.date, stored["Close"])) == {day: 11.0, new_day: 12.0}
