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
        (
            pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[ms]").tz_localize("UTC"),
            "tz_aware_already_ms",
        ),
    ],
    ids=["ns", "ms", "s", "date_objects", "tz_aware_utc", "tz_aware_non_utc", "tz_aware_already_ms"],
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


def test_ensure_schema_skips_to_datetime_when_column_already_datetime(monkeypatch):
    """Regression test for #8095: pandas' ``pd.to_datetime(..., errors="coerce")``
    is expensive even on an already-datetime64 column, because its
    ``should_cache`` heuristic iterates every row. This is the actual hot path
    behind the slow sector/region/group aggregation endpoints under
    ``offline_mode`` -- reading each ticker's (potentially multi-thousand-row)
    cached parquet history re-runs this "parsing" on every request. When the
    ``Date`` column is already a real datetime64 dtype there is nothing to
    parse, so ``_ensure_schema`` must not call ``pd.to_datetime`` at all."""
    cache = import_cache()

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[ms]"),
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [100, 200],
            "Ticker": ["ABC", "ABC"],
            "Source": ["SRC", "SRC"],
        }
    )

    calls = []
    real_to_datetime = pd.to_datetime

    def spy_to_datetime(*args, **kwargs):
        calls.append((args, kwargs))
        return real_to_datetime(*args, **kwargs)

    monkeypatch.setattr(cache.pd, "to_datetime", spy_to_datetime)

    result = cache._ensure_schema(df)

    assert calls == []
    assert result["Date"].dtype == "datetime64[ms]"


def test_ensure_schema_still_parses_non_datetime_date_column(monkeypatch):
    """Non-datetime64 ``Date`` inputs (e.g. raw ``datetime.date`` objects or
    strings) still need parsing, so the fast-path in the previous test must not
    skip ``pd.to_datetime`` for them."""
    cache = import_cache()

    calls = []
    real_to_datetime = pd.to_datetime

    def spy_to_datetime(*args, **kwargs):
        calls.append((args, kwargs))
        return real_to_datetime(*args, **kwargs)

    monkeypatch.setattr(cache.pd, "to_datetime", spy_to_datetime)

    df = pd.DataFrame(
        {
            "Date": [date(2024, 1, 1), date(2024, 1, 2)],
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

    assert len(calls) == 1
    assert result["Date"].dtype == "datetime64[ms]"


def test_ensure_schema_skips_astype_dropna_and_reindex_when_already_conforming(monkeypatch):
    """Regression test for #8137: profiling showed ``.dropna()`` alone cost
    2.39s of _ensure_schema's 4.45s for 1453 calls on an already-valid,
    already-sliced 64-row frame (the exact shape ``apply_date_range``'s
    output takes at the three call sites in ``_memoized_range_cached``) --
    dropna's full-frame mask + reindex machinery runs even though there is
    nothing to drop. When the ``Date`` column is already ``datetime64[ms]``
    with no nulls and the columns already match ``EXPECTED_COLS`` exactly,
    ``_ensure_schema`` must skip ``.astype``, ``.dropna``, and the final
    column reindex entirely rather than just being correct despite doing
    the (redundant) work.
    """
    cache = import_cache()

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[ms]"),
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [100, 200],
            "Ticker": ["ABC", "ABC"],
            "Source": ["SRC", "SRC"],
        }
    )
    assert list(df.columns) == cache.EXPECTED_COLS

    astype_calls = []
    real_astype = pd.Series.astype

    def spy_astype(self, *args, **kwargs):
        astype_calls.append((args, kwargs))
        return real_astype(self, *args, **kwargs)

    dropna_calls = []
    real_dropna = pd.DataFrame.dropna

    def spy_dropna(self, *args, **kwargs):
        dropna_calls.append((args, kwargs))
        return real_dropna(self, *args, **kwargs)

    monkeypatch.setattr(pd.Series, "astype", spy_astype)
    monkeypatch.setattr(pd.DataFrame, "dropna", spy_dropna)

    result = cache._ensure_schema(df)

    assert astype_calls == []
    assert dropna_calls == []
    assert result is df
    assert list(result.columns) == cache.EXPECTED_COLS
    assert result["Date"].dtype == "datetime64[ms]"


def test_ensure_schema_still_drops_nat_rows_when_present():
    """The fast path in #8137 must not skip dropping NaT rows -- only skip
    the work when there is genuinely nothing to drop."""
    cache = import_cache()

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", None, "2024-01-03"]).astype("datetime64[ms]"),
            "Open": [1.0, 2.0, 3.0],
            "High": [1.5, 2.5, 3.5],
            "Low": [0.5, 1.5, 2.5],
            "Close": [1.2, 2.2, 3.2],
            "Volume": [100, 200, 300],
            "Ticker": ["ABC", "ABC", "ABC"],
            "Source": ["SRC", "SRC", "SRC"],
        }
    )

    result = cache._ensure_schema(df)

    assert list(result["Date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-03"]


def test_ensure_schema_still_reindexes_columns_out_of_order():
    """The column-reindex skip in #8137 must only fire when columns already
    match ``EXPECTED_COLS`` exactly -- an out-of-order or extra-column frame
    must still be reindexed."""
    cache = import_cache()

    df = pd.DataFrame(
        {
            "Ticker": ["ABC", "ABC"],
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]).astype("datetime64[ms]"),
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [100, 200],
            "Source": ["SRC", "SRC"],
            "Extra": ["x", "y"],
        }
    )

    result = cache._ensure_schema(df)

    assert list(result.columns) == cache.EXPECTED_COLS


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


def test_rolling_cache_persists_volume_only_correction(cache_store):
    """A correction to a value column other than Close (here Volume) is also saved (#7914)."""
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)
    fetched = _day_frame(cache, day, 10.0)
    fetched["Volume"] = 200

    result = _run(cache, cache_path, fetched)

    assert len(saves) == 1
    assert result.loc[result["Date"].dt.date == day, "Volume"].tolist() == [200]
    stored = cache._load_parquet(cache_path)
    assert stored.loc[stored["Date"].dt.date == day, "Volume"].tolist() == [200]


def test_rolling_cache_duplicate_fetched_dates_keep_last_row(cache_store):
    """A fetch returning the same cached date twice applies the last row once (#7914)."""
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)
    fetched = pd.concat([_day_frame(cache, day, 10.5), _day_frame(cache, day, 11.0)], ignore_index=True)

    result = _run(cache, cache_path, fetched)

    assert len(saves) == 1
    assert result.loc[result["Date"].dt.date == day, "Close"].tolist() == [11.0]
    stored = cache._load_parquet(cache_path)
    assert stored.loc[stored["Date"].dt.date == day, "Close"].tolist() == [11.0]


def test_rolling_cache_duplicate_cached_dates_collapse_without_save(cache_store):
    """A cache holding a date twice serves it once, and an identical fetch still skips the save."""
    cache, cache_path, saves = cache_store
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 5)
    day = window_end - timedelta(days=1)
    cache._save_parquet(
        pd.concat([_day_frame(cache, day, 10.0), _day_frame(cache, day, 10.0)], ignore_index=True),
        cache_path,
    )
    saves.clear()

    result = _run(cache, cache_path, _day_frame(cache, day, 10.0))

    assert saves == []
    assert result.loc[result["Date"].dt.date == day, "Close"].tolist() == [10.0]


@pytest.mark.parametrize("nat_date", [True, False], ids=["all_na_incl_date", "cached_date_all_na_values"])
def test_rolling_cache_all_na_fetch_does_not_save(cache_store, nat_date):
    """An all-NA fetch over a non-empty cache neither saves nor overwrites (#7877, #7914).

    A NaT-dated frame is dropped by ``_ensure_schema`` before the merge; a cached
    date with all-NaN values reaches ``_merge_fetched`` but has no Close, so it is
    not a correction.
    """
    cache, cache_path, saves = cache_store
    day = _seed_close_10(cache, cache_path, saves)
    fetched = pd.DataFrame(
        {
            "Date": [pd.NaT if nat_date else pd.Timestamp(day)],
            **{col: [float("nan")] for col in ("Open", "High", "Low", "Close", "Volume")},
            "Ticker": [None],
            "Source": [None],
        }
    )

    result = _run(cache, cache_path, fetched)

    assert saves == []
    assert result.loc[result["Date"].dt.date == day, "Close"].tolist() == [10.0]


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


def _seed_stale_meta_cache(cache, ticker: str, exchange: str) -> date:
    """Write a meta parquet whose last row is two weekdays before the rolling window end."""
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 60)
    last = window_end - timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    dates = pd.bdate_range(end=last, periods=90)
    frame = pd.DataFrame(
        {
            "Date": dates,
            "Open": 1.0,
            "High": 1.0,
            "Low": 1.0,
            "Close": [float(i) for i in range(len(dates))],
            "Volume": 0,
            "Ticker": ticker,
            "Source": "SRC",
        }
    )
    cache._save_parquet(frame, cache.meta_timeseries_cache_path(ticker, exchange))
    return last


def _clear_meta_lrus(cache):
    cache._load_meta_timeseries_cached.cache_clear()
    cache._memoized_range_cached.cache_clear()
    cache._load_meta_parquet_cached.cache_clear()
    cache._CACHE_FILE_MTIMES.clear()


def test_cache_only_serves_stale_cache_without_fetching(monkeypatch, tmp_path):
    """In cache-only mode a stale ticker is served from parquet and no price source is called (#7898)."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "ABC", "L")

    calls = []

    def exploding_fetch(**kwargs):
        calls.append(kwargs)
        raise AssertionError("cache-only mode must not call a price source")

    monkeypatch.setattr(cache, "fetch_meta_timeseries", exploding_fetch)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range(
            "ABC", "L", start_date=last + timedelta(days=1), end_date=last + timedelta(days=1)
        )

    assert calls == []
    # The requested day isn't cached, so load_meta_timeseries_range walks back
    # to the most recent cached close -- the same previous-close fallback the
    # live path uses when a fetch comes back empty.
    assert not df.empty
    assert df["Date"].dt.date.iloc[0] == last
    assert cache.is_cache_only() is False


def test_cache_only_read_is_not_reused_by_live_callers(monkeypatch, tmp_path):
    """A cache-only read must not be memoised under the key a live caller uses (#7898).

    Otherwise the background refresh would get the stale cache-only result back
    and never fetch, so the parquet cache would silently stop updating.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "ABC", "L")
    day = last + timedelta(days=1)

    calls = []

    def recording_fetch(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr(cache, "fetch_meta_timeseries", recording_fetch)

    with cache.cache_only():
        cache.load_meta_timeseries_range("ABC", "L", start_date=day, end_date=day)
        cache.load_meta_timeseries("ABC", "L", 60)
    assert calls == []

    cache.load_meta_timeseries_range("ABC", "L", start_date=day, end_date=day)
    assert calls, "live caller should reach the price source after a cache-only read"


@pytest.mark.parametrize("offline", [False, True])
def test_cache_only_without_cache_file_returns_empty_without_fetching(monkeypatch, tmp_path, offline):
    """A newly added holding with no cache file is unpriced, not blocked, in cache-only mode (#7898).

    Covers offline mode too: there the loaders would normally switch offline mode
    off and fetch live on a cache miss, which cache-only mode must not do.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", offline)
    monkeypatch.setattr(cache.config, "offline_mode", offline)
    _clear_meta_lrus(cache)

    def exploding_fetch(**_kwargs):
        raise AssertionError("cache-only mode must not call a price source")

    monkeypatch.setattr(cache, "fetch_meta_timeseries", exploding_fetch)
    day = datetime.today().date() - timedelta(days=3)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("NEW", "L", start_date=day, end_date=day)

    assert df.empty


def test_offline_mode_without_cache_only_still_falls_back_live(monkeypatch, tmp_path):
    """Offline-mode behaviour outside cache-only mode is unchanged: a cache miss still goes live (#7898)."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    monkeypatch.setattr(cache.config, "offline_mode", True)
    _clear_meta_lrus(cache)

    calls = []

    def recording_fetch(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr(cache, "fetch_meta_timeseries", recording_fetch)
    day = datetime.today().date() - timedelta(days=3)

    cache.load_meta_timeseries_range("NEW", "L", start_date=day, end_date=day)

    assert calls, "offline mode should still fall back to a live fetch on a cache miss"


def test_memoized_range_honours_cache_only_argument_outside_context(monkeypatch, tmp_path):
    """The LRU-keyed ``cache_only`` argument alone must prevent fetching (#7898).

    Guards against the key and the behaviour drifting apart: the argument is
    acted on directly rather than via the context variable.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "ABC", "L")

    def exploding_fetch(**_kwargs):
        raise AssertionError("cache_only=True must not call a price source")

    monkeypatch.setattr(cache, "fetch_meta_timeseries", exploding_fetch)
    day = (last + timedelta(days=1)).isoformat()

    assert cache.is_cache_only() is False
    assert cache._memoized_range_cached("ABC", "L", day, day, True).empty
    assert cache._memoized_range_cached("NEW", "L", day, day, True).empty
    served = cache._memoized_range_cached("ABC", "L", last.isoformat(), last.isoformat(), True)
    assert served["Date"].dt.date.tolist() == [last]


def test_cache_only_stale_ticker_priced_at_last_cached_close(monkeypatch, tmp_path):
    """End to end: a stale ticker priced in cache-only mode is flagged stale, not blocked (#7898).

    The reporting date's close is missing from the parquet, so ``enrich_holding``
    must price the holding at the last cached close with ``is_stale=True``
    without calling a price source. (The range loader's few-day lookback serves
    that close for the reporting date itself, so ``latest_source`` is the cached
    row's source rather than ``"previous_close"``.)
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "FOO", "L")
    last_close = float(len(pd.bdate_range(end=last, periods=90)) - 1)

    def exploding_fetch(**_kwargs):
        raise AssertionError("cache-only mode must not call a price source")

    monkeypatch.setattr(cache, "fetch_meta_timeseries", exploding_fetch)

    import backend.common.holding_utils as hu
    import backend.common.portfolio_utils as pu
    from backend.common.constants import ACQUIRED_DATE, COST_BASIS_GBP, TICKER, UNITS

    monkeypatch.setattr(hu, "load_meta_timeseries_range", cache.load_meta_timeseries_range)
    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {"currency": "GBP"})
    monkeypatch.setattr(hu, "get_scaling_override", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(hu, "get_effective_cost_basis_gbp", lambda h, cache, price_hint=None: 0.0)
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})

    # Report on the weekday after ``last``, whose close the cache doesn't have.
    reporting = last + timedelta(days=1)
    while reporting.weekday() >= 5:
        reporting += timedelta(days=1)
    today = reporting + timedelta(days=1)

    holding = {TICKER: "FOO.L", UNITS: 10, COST_BASIS_GBP: 0.0, ACQUIRED_DATE: "2020-01-01"}
    with cache.cache_only():
        result = hu.enrich_holding(holding, today, price_cache={})

    assert result["price"] == pytest.approx(last_close)
    assert result["market_value_gbp"] == pytest.approx(10 * last_close)
    assert result["is_stale"] is True


def test_cache_only_read_sees_background_refresh_of_parquet(monkeypatch, tmp_path):
    """A memoised cache-only read must not outlive a parquet update (#7898).

    When the background refresh rewrites the file, the mtime check in
    _invalidate_meta_caches_if_stale clears both LRUs, cache-only entries
    included, so the next page request sees the new close.
    """
    import os

    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "ABC", "L")
    day = last + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)

    def exploding_fetch(**_kwargs):
        raise AssertionError("cache-only mode must not call a price source")

    monkeypatch.setattr(cache, "fetch_meta_timeseries", exploding_fetch)

    with cache.cache_only():
        before = cache.load_meta_timeseries_range("ABC", "L", start_date=day, end_date=day)
    assert before["Date"].dt.date.iloc[0] == last

    # Simulate the background refresh appending the missing close.
    path = cache.meta_timeseries_cache_path("ABC", "L")
    refreshed = pd.concat([cache._load_parquet(path), _single_row(cache, day)], ignore_index=True)
    cache._save_parquet(refreshed, path)
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))

    with cache.cache_only():
        after = cache.load_meta_timeseries_range("ABC", "L", start_date=day, end_date=day)
    assert after["Date"].dt.date.iloc[0] == day


# ──────────────────────────────────────────────────────────────
# Warm per-ticker parquet cache (#8105)
# ──────────────────────────────────────────────────────────────
def test_load_meta_parquet_cached_shares_one_read_across_different_windows(monkeypatch, tmp_path):
    """Two different date windows against the same ticker share one parquet read (#8105).

    Before this cache, ``_memoized_range_cached``'s ``cache_only`` branch (the
    page-request path -- see ``/portfolio/{owner}/sectors`` and friends) called
    ``_load_parquet`` directly, so every distinct (ticker, start, end) tuple --
    which different holdings for the same owner routinely produce -- re-read
    and re-validated the *entire* per-ticker history. ``_load_meta_parquet_cached``
    shares one validated read across those different windows within a process.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "ABC", "L")

    reads = []
    real_load_parquet = cache._load_parquet

    def counting_load_parquet(path):
        reads.append(path)
        return real_load_parquet(path)

    monkeypatch.setattr(cache, "_load_parquet", counting_load_parquet)

    with cache.cache_only():
        first = cache.load_meta_timeseries_range("ABC", "L", start_date=last, end_date=last)
        second = cache.load_meta_timeseries_range(
            "ABC", "L", start_date=last - timedelta(days=1), end_date=last - timedelta(days=1)
        )

    assert not first.empty
    assert not second.empty
    assert first["Date"].dt.date.iloc[0] == last
    assert second["Date"].dt.date.iloc[0] == last - timedelta(days=1)
    # One underlying parquet read serves both distinct windows.
    assert len(reads) == 1


def test_load_meta_parquet_cached_invalidated_alongside_other_meta_lrus(monkeypatch, tmp_path):
    """``_invalidate_meta_caches_if_stale`` clears the warm parquet cache too (#8105, #7877).

    Extends the existing "both meta LRUs are cleared on a real mtime change"
    guarantee (#7877) to the new warm per-ticker cache: it must never serve
    data staler than ``_load_meta_timeseries_cached``/``_memoized_range_cached``
    would, and it must not be cleared on a no-op rewrite either.
    """
    import os

    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.config, "offline_mode", False)
    _clear_meta_lrus(cache)
    last = _seed_stale_meta_cache(cache, "ABC", "L")

    with cache.cache_only():
        before = cache.load_meta_timeseries_range("ABC", "L", start_date=last, end_date=last)
    assert before["Close"].iloc[0] is not None
    assert cache._load_meta_parquet_cached.cache_info().currsize == 1

    # A corrected close for the same cached date, written directly (as a
    # background refresh would), with the mtime bumped forward so the change
    # is observed regardless of filesystem mtime granularity.
    path = cache.meta_timeseries_cache_path("ABC", "L")
    updated = cache._load_parquet(path).copy()
    updated.loc[updated["Date"].dt.date == last, "Close"] = 999.0
    cache._save_parquet(updated, path)
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))

    cache._invalidate_meta_caches_if_stale("ABC", "L")
    assert cache._load_meta_parquet_cached.cache_info().currsize == 0

    with cache.cache_only():
        after = cache.load_meta_timeseries_range("ABC", "L", start_date=last, end_date=last)
    assert after["Close"].iloc[0] == 999.0


def test_rolling_cache_does_not_mutate_shared_loader_cache(monkeypatch, tmp_path):
    """``_rolling_cache`` must never mutate the DataFrame its ``loader`` returns in place.

    DeepSeek's PR review on #8105 flagged that ``_load_meta_parquet_cached`` --
    an ``lru_cache`` over the raw parquet read, shared across every caller in
    the process -- is passed as ``_rolling_cache``'s ``loader`` for the live
    meta path. ``_rolling_cache`` is the *write* path: it merges fetched data
    into ``existing`` and may save the result. If any operation on
    ``existing`` mutated it in place (e.g. ``.loc[...] = ...``,
    ``inplace=True``, or a ``concat``/``assign`` that reused the buffer), the
    shared cached object would be corrupted for every other caller reading the
    same lru entry, including read-only page-request paths that expect
    on-disk contents.

    Reading ``_rolling_cache`` and ``_merge_fetched`` shows every
    transformation of ``existing`` -- ``.copy()``, boolean ``.loc[mask]``
    selection, ``pd.concat``, ``.sort_values()``/``.reset_index()`` -- is
    called without ``inplace=True`` and produces a new object rather than
    writing back into the original buffers, so this is safe. This test proves
    that empirically rather than trusting the reading: it primes the shared
    ``_load_meta_parquet_cached`` entry, drives a real write through
    ``_rolling_cache`` using that entry as the loader, confirms (via a
    ``_load_parquet`` call-count spy) that both the write and the later
    re-check hit the *same* lru entry rather than a fresh disk read, and then
    asserts that entry's object is still byte-for-byte identical to a
    snapshot taken before the write.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    cache_path = cache.meta_timeseries_cache_path("ABC", "L")
    expected = _seed_existing_parquet(cache, cache_path, days=5)

    real_load_parquet = cache._load_parquet
    read_calls = []

    def counting_load_parquet(path):
        read_calls.append(path)
        return real_load_parquet(path)

    monkeypatch.setattr(cache, "_load_parquet", counting_load_parquet)

    # Prime the shared lru_cache entry with one real disk read.
    cached_obj = cache._load_meta_parquet_cached(cache_path)
    assert read_calls == [cache_path]
    snapshot = cached_obj.copy(deep=True)

    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 5)
    assert window_end not in set(expected["Date"].dt.date)

    # Drive the write path with the shared, cached loader -- exactly how
    # _load_meta_timeseries_cached wires it for live meta-timeseries calls.
    result = cache._rolling_cache(
        lambda **_kwargs: _single_row(cache, window_end),
        cache_path,
        {},
        days=5,
        ticker="ABC",
        exchange="L",
        loader=cache._load_meta_parquet_cached,
    )
    assert window_end in set(result["Date"].dt.date)

    # Still only the one disk read: _rolling_cache's `existing` was served
    # from the lru_cache entry primed above, confirming this genuinely
    # exercises the shared-object hazard rather than a fresh miss.
    assert read_calls == [cache_path]

    # The shared cached object itself (re-fetched from the still-warm
    # lru_cache entry -- another disk-read-free hit) must be unchanged: the
    # write above must not have mutated it in place.
    still_cached = cache._load_meta_parquet_cached(cache_path)
    assert read_calls == [cache_path]
    assert_frame_equal(still_cached, snapshot)


def test_memoized_range_fast_ensure_schema_does_not_alias_shared_warm_cache(monkeypatch, tmp_path):
    """#8137's ``_ensure_schema`` fast path can return the exact same object it
    was given (rather than always allocating a new one via ``df[EXPECTED_COLS]``)
    when the input already conforms. ``_memoized_range_cached`` calls
    ``_ensure_schema(apply_date_range(existing, ...))`` where ``existing`` is
    the shared ``_load_meta_parquet_cached`` warm-cache entry -- if
    ``apply_date_range`` didn't always copy before slicing, this fast path
    could hand back an alias of the shared cache entry, and a caller
    mutating the "own copy" they think they have would corrupt every other
    reader. ``apply_date_range`` already ``.copy()``s on every path (verified
    directly, not assumed), and the outer ``_memoized_range``/
    ``load_meta_timeseries`` wrappers add one more ``.copy()`` on top -- this
    test proves the whole chain empirically: mutate the frame returned by
    ``_memoized_range`` and confirm the shared warm-cache entry is untouched.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)

    cache_path = cache.meta_timeseries_cache_path("ABC", "L")
    expected = _seed_existing_parquet(cache, cache_path, days=10)
    start_date = expected["Date"].min().date()
    end_date = expected["Date"].max().date()

    # Prime the shared _load_meta_parquet_cached entry and snapshot it.
    cached_obj = cache._load_meta_parquet_cached(cache_path)
    snapshot = cached_obj.copy(deep=True)

    result = cache._memoized_range(
        "ABC",
        "L",
        start_date.isoformat(),
        end_date.isoformat(),
    )

    # Mutate the caller-visible result in place -- this must not be able to
    # reach the shared warm-cache entry through any aliasing introduced by
    # skipping _ensure_schema's defensive reindex.
    result["Close"] = -1.0
    result.drop(result.index, inplace=True)

    still_cached = cache._load_meta_parquet_cached(cache_path)
    assert_frame_equal(still_cached, snapshot)


def test_load_parquet_fast_path_never_shares_an_object_across_calls(monkeypatch, tmp_path):
    """Audit for #8137's review: every ``_ensure_schema`` caller other than
    ``_memoized_range_cached`` was checked for mutation-after-call risk, not
    just re-read. ``_load_parquet`` (used directly by
    ``load_cached_meta_timeseries_full``, which ``backend/routes/data_quality_admin.py``
    mutates in place via ``df["Ticker"] = ticker`` without copying first) does
    a fresh ``pd.read_parquet`` on every call -- unlike ``_memoized_range_cached``,
    it is never wrapped in an ``lru_cache``, so no two calls can ever return
    the same object for ``_ensure_schema``'s fast path to alias. This test
    proves that directly: two back-to-back reads of the same file must never
    be the same object, and mutating one must never affect the other or a
    fresh third read.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()

    cache_path = cache.meta_timeseries_cache_path("ABC", "L")
    _seed_existing_parquet(cache, cache_path, days=5)

    first = cache.load_cached_meta_timeseries_full("ABC", "L")
    second = cache.load_cached_meta_timeseries_full("ABC", "L")
    assert first is not second
    expected_dates = list(second["Date"].dt.date)

    first["Ticker"] = "MUTATED"
    first.drop(first.index, inplace=True)

    assert list(second["Ticker"].unique()) != ["MUTATED"]
    assert not second.empty

    third = cache.load_cached_meta_timeseries_full("ABC", "L")
    assert list(third["Date"].dt.date) == expected_dates
