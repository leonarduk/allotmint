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


def test_cache_only_stale_ticker_enriches_as_previous_close(monkeypatch, tmp_path):
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
