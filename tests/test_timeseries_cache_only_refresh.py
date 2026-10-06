"""Cache-only page reads queue stale tickers for a background refresh (#7917).

Builds on the cache-only mode from #7898 (tests in
``test_timeseries_cache_merge.py``): these cover what a cache-only read does
when the cache is short -- the last-cached-close fallback, the FX cache, and
the refresh queue that brings the parquet files up to date afterwards.
"""

import importlib
import sys
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.timeseries import refresh_queue


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    mod = import_cache()
    monkeypatch.setattr(mod, "OFFLINE_MODE", False)
    monkeypatch.setattr(mod.config, "offline_mode", False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    currencies = {"L": "GBP", "N": "USD"}
    monkeypatch.setattr(mod, "get_instrument_meta", lambda full: {"currency": currencies[full.rsplit(".", 1)[1]]})
    return mod


def _explode(name):
    def fetch(*_args, **_kwargs):
        raise AssertionError(f"cache-only read must not call {name}")

    return fetch


@pytest.fixture
def no_live_calls(cache, monkeypatch):
    """Make every live price and FX source in the cache module fail the test if called."""
    monkeypatch.setattr(cache, "fetch_meta_timeseries", _explode("fetch_meta_timeseries"))
    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", _explode("fetch_fx_rate_range_live"))
    import backend.utils.fx_rates as fx_rates

    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", _explode("fx_rates.fetch_fx_rate_range_live"))
    cache.fetch_fx_rate_range.cache_clear()


def _weekday_back(day: date, n: int) -> date:
    while n:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


def _seed_meta(cache, ticker: str, exchange: str, last: date, close: float = 10.0) -> None:
    dates = pd.bdate_range(end=last, periods=90)
    frame = pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": 0,
            "Ticker": ticker,
            "Source": "Yahoo",
        }
    )
    cache._save_parquet(frame, cache.meta_timeseries_cache_path(ticker, exchange))


def _seed_fx(cache, curr: str, last: date, rate: float) -> None:
    dates = pd.bdate_range(end=last, periods=30)
    frame = pd.DataFrame({"Date": dates, "Rate": rate})
    path = cache._fx_cache_path(curr)
    cache._ensure_local_dir(path)
    frame.to_parquet(path, index=False)


def _target(cache) -> date:
    return cache._last_close_target()


def test_cache_only_serves_last_cached_close_beyond_walk_back(cache, no_live_calls):
    """A ticker stale by more than the 5-day walk-back is priced at its last close, not blank."""
    last = _weekday_back(_target(cache), 8)
    _seed_meta(cache, "OLD", "L", last, close=12.5)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("OLD", "L", start_date=_target(cache), end_date=_target(cache))

    assert df["Date"].dt.date.tolist() == [last]
    assert df["Close"].tolist() == [12.5]
    assert refresh_queue.pending() == [("OLD", "L")]


def test_cache_only_fallback_needs_a_close_on_or_before_the_end_date(cache, no_live_calls):
    """The fallback never serves a close from after the requested range."""
    last = _weekday_back(_target(cache), 2)
    _seed_meta(cache, "ABC", "L", last)
    before_history = last - timedelta(days=400)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("ABC", "L", start_date=before_history, end_date=before_history)

    assert df.empty


def test_cache_only_queues_each_stale_ticker_once_and_skips_fresh_ones(cache, no_live_calls):
    _seed_meta(cache, "STALE", "L", _weekday_back(_target(cache), 2))
    _seed_meta(cache, "FRESH", "L", _target(cache))
    day = _target(cache)

    with cache.cache_only():
        for _ in range(3):
            cache.load_meta_timeseries_range("STALE", "L", start_date=day, end_date=day)
            cache.load_meta_timeseries_range("FRESH", "L", start_date=day, end_date=day)
            cache.load_meta_timeseries_range("NEW", "L", start_date=day, end_date=day)
            cache._memoized_range_cached.cache_clear()

    assert refresh_queue.pending() == [("STALE", "L"), ("NEW", "L")]


def test_cache_only_converts_with_the_fx_cache(cache, no_live_calls):
    """A USD close is converted from the FX parquet; no FX source is called."""
    day = _target(cache)
    _seed_meta(cache, "AAPL", "N", day, close=100.0)
    _seed_fx(cache, "USD", day, rate=0.75)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("AAPL", "N", start_date=day, end_date=day)

    assert df["Close_gbp"].tolist() == [pytest.approx(75.0)]
    assert refresh_queue.pending() == []


def test_cache_only_carries_the_last_cached_fx_rate_forward_and_queues(cache, no_live_calls):
    day = _target(cache)
    _seed_meta(cache, "AAPL", "N", day, close=100.0)
    _seed_fx(cache, "USD", _weekday_back(day, 3), rate=0.75)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("AAPL", "N", start_date=day, end_date=day)

    assert df["Close_gbp"].tolist() == [pytest.approx(75.0)]
    assert refresh_queue.pending() == [("AAPL", "N")]


def test_cache_only_without_fx_cache_uses_fallback_rate_and_queues(cache, no_live_calls):
    """No FX file yet: same approximate constant a failed live fetch returns, never a fetch."""
    from backend.utils.fx_rates import FALLBACK_RATES

    day = _target(cache)
    _seed_meta(cache, "AAPL", "N", day, close=100.0)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("AAPL", "N", start_date=day, end_date=day)

    assert df["Close_gbp"].tolist() == [pytest.approx(100.0 * FALLBACK_RATES[("USD", "GBP")])]
    assert refresh_queue.pending() == [("AAPL", "N")]


def test_cache_only_ignores_offline_mode_fx_proxy_and_live_fallback(cache, no_live_calls, monkeypatch):
    """Offline mode's FX cache miss goes to the proxy, then Yahoo; cache-only must not."""
    import requests

    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    monkeypatch.setattr(cache.config, "fx_proxy_url", "http://fx.invalid")
    monkeypatch.setattr(requests, "get", _explode("requests.get"))
    monkeypatch.setattr(cache, "fetch_fx_rate_range", _explode("fetch_fx_rate_range"))
    day = _target(cache)
    _seed_meta(cache, "AAPL", "N", day, close=100.0)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("AAPL", "N", start_date=day, end_date=day)

    assert not df.empty


def test_refresh_fx_cache_appends_new_dates_and_skips_no_op_writes(cache, monkeypatch):
    import os

    last = _weekday_back(_target(cache), 2)
    _seed_fx(cache, "USD", last, rate=0.75)
    path = cache._fx_cache_path("USD")
    requested = []

    def fake_live(base, quote, start, end):
        requested.append((base, quote, start, end))
        days = pd.bdate_range(start, end).date
        return pd.DataFrame({"Date": days, "Rate": 0.8})

    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", fake_live)

    assert cache.refresh_fx_cache("USD") is True
    assert requested[0][:3] == ("USD", "GBP", last + timedelta(days=1))
    stored = pd.read_parquet(path)
    assert stored["Date"].is_monotonic_increasing and not stored["Date"].duplicated().any()
    assert stored["Rate"].iloc[-1] == pytest.approx(0.8)

    mtime = os.stat(path).st_mtime
    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", lambda *a: pd.DataFrame({"Date": [], "Rate": []}))
    assert cache.refresh_fx_cache("USD") is False
    assert os.stat(path).st_mtime == mtime
    assert cache.refresh_fx_cache("GBP") is False


def test_refresh_fx_cache_never_persists_the_fallback_constant(cache, monkeypatch):
    """A failed live fetch leaves no FX file, so cache-only reads keep queueing a refresh."""
    import backend.utils.fx_rates as fx_rates

    def failing_history(*_args, **_kwargs):
        raise ConnectionError("yahoo unreachable")

    class FailingTicker:
        def __init__(self, _pair):
            self.history = failing_history

    monkeypatch.setattr(fx_rates.yf, "Ticker", FailingTicker)
    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", fx_rates.fetch_fx_rate_range_live)

    assert cache.refresh_fx_cache("USD") is False
    assert cache._read_fx_parquet(cache._fx_cache_path("USD")).empty


def test_read_fx_parquet_keeps_the_last_stored_rate_per_date(cache):
    """A date stored more than once reads as its last stored row.

    Each of 60 dates is stored three times, in three passes. That is enough
    rows for an unstable sort to reorder equal dates, so the test fails unless
    the read sorts stably before dropping duplicates.
    """
    days = pd.date_range("2024-01-01", periods=60, freq="D")
    stored = pd.DataFrame({"Date": list(days) * 3, "Rate": [0.7] * 60 + [0.8] * 60 + [0.9] * 60})
    path = cache._fx_cache_path("USD")
    cache._ensure_local_dir(path)
    stored.to_parquet(path, index=False)

    fx = cache._read_fx_parquet(path)

    assert list(fx["Date"]) == list(days)
    assert set(fx["Rate"]) == {0.9}


def test_drain_refreshes_stale_ticker_and_next_cache_only_read_sees_it(cache, monkeypatch):
    """End to end: queued by a page read, refreshed live by the worker, then served fresh."""
    import os

    day = _target(cache)
    last = _weekday_back(day, 2)
    _seed_meta(cache, "ABC", "L", last, close=10.0)
    monkeypatch.setattr(cache, "fetch_meta_timeseries", _explode("fetch_meta_timeseries"))

    with cache.cache_only():
        before = cache.load_meta_timeseries_range("ABC", "L", start_date=day, end_date=day)
    assert before["Date"].dt.date.tolist() == [last]
    assert refresh_queue.pending() == [("ABC", "L")]

    fetched = []

    def live_fetch(**kwargs):
        fetched.append(kwargs)
        days = pd.bdate_range(kwargs["start_date"], kwargs["end_date"])
        return pd.DataFrame(
            {
                "Date": days,
                "Open": 11.0,
                "High": 11.0,
                "Low": 11.0,
                "Close": 11.0,
                "Volume": 0,
                "Ticker": "ABC",
                "Source": "Yahoo",
            }
        )

    monkeypatch.setattr(cache, "fetch_meta_timeseries", live_fetch)
    # The refresh must not run in cache-only mode even when drained from inside one.
    with cache.cache_only():
        assert refresh_queue.drain() == 1
    assert fetched, "the drain should call the live price source"
    assert refresh_queue.pending() == []

    path = cache.meta_timeseries_cache_path("ABC", "L")
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    monkeypatch.setattr(cache, "fetch_meta_timeseries", _explode("fetch_meta_timeseries"))

    with cache.cache_only():
        after = cache.load_meta_timeseries_range("ABC", "L", start_date=day, end_date=day)
    assert after["Date"].dt.date.tolist() == [day]
    assert after["Close"].tolist() == [11.0]


def test_ticker_is_not_requeued_within_the_retry_cooldown(cache, monkeypatch):
    monkeypatch.setattr(refresh_queue, "_refresh_one", _explode("_refresh_one"))

    assert refresh_queue.enqueue("abc", "l") is True
    assert refresh_queue.enqueue("ABC", "L") is False  # already waiting
    assert refresh_queue.drain() == 0  # the failed refresh is logged, not raised
    assert refresh_queue.enqueue("ABC", "L") is False  # attempted within the cooldown

    monkeypatch.setattr(refresh_queue, "_RETRY_COOLDOWN_SECONDS", 0)
    assert refresh_queue.enqueue("ABC", "L") is True


@pytest.mark.parametrize("reason", ["offline", "lambda"])
def test_nothing_is_queued_offline_or_on_lambda(cache, monkeypatch, reason):
    """Offline mode never fetches; Lambda relies on the scheduled PriceRefreshLambda."""
    if reason == "offline":
        monkeypatch.setattr(cache.config, "offline_mode", True)
    else:
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "allotmint-backend")

    assert refresh_queue.enqueue("ABC", "L") is False
    assert refresh_queue.pending() == []


def test_enqueue_starts_one_worker_that_drains_the_queue(cache, monkeypatch):
    import threading

    refreshed = []
    release = threading.Event()

    def slow_refresh(ticker, exchange):
        release.wait(5)
        refreshed.append((ticker, exchange))

    monkeypatch.setattr(refresh_queue, "_refresh_one", slow_refresh)
    monkeypatch.setattr(refresh_queue, "autostart", True)
    monkeypatch.setattr(refresh_queue, "_worker", None)

    refresh_queue.enqueue("AAA", "L")
    worker = refresh_queue._worker
    refresh_queue.enqueue("BBB", "L")
    assert refresh_queue._worker is worker
    release.set()
    worker.join(5)

    assert not worker.is_alive()
    assert refreshed == [("AAA", "L"), ("BBB", "L")]


def test_cold_group_portfolio_build_makes_no_live_price_calls(cache, no_live_calls, monkeypatch):
    """DONE for #7917: a cold group build with stale caches prices every holding and fetches nothing.

    Stale tickers (one past the 5-day walk-back, one USD with a stale FX
    cache) are priced from cache, flagged stale, and queued for refresh.
    """
    from unittest.mock import patch

    import backend.common.group_portfolio as gp
    import backend.common.holding_utils as hu
    import backend.common.portfolio_utils as pu
    from backend.common.constants import ACCOUNTS, HOLDINGS
    from backend.common.data_loader import OwnerSummaryRecord

    day = _target(cache)
    _seed_meta(cache, "VWRL", "L", _weekday_back(day, 8), close=100.0)
    _seed_meta(cache, "AAPL", "N", _weekday_back(day, 2), close=200.0)
    _seed_meta(cache, "GSK", "L", day, close=15.0)
    _seed_fx(cache, "USD", _weekday_back(day, 4), rate=0.75)

    # holding_utils and group_portfolio bound the original cache module's
    # loader and cache_only() at import; point them at this reloaded copy.
    monkeypatch.setattr(hu, "load_meta_timeseries_range", cache.load_meta_timeseries_range)
    monkeypatch.setattr(gp, "cache_only", cache.cache_only)
    monkeypatch.setattr(hu, "get_instrument_meta", lambda full: cache.get_instrument_meta(full))
    monkeypatch.setattr(hu, "get_scaling_override", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})

    portfolios = [
        {
            "owner": "alex",
            ACCOUNTS: [
                {
                    "currency": "GBP",
                    HOLDINGS: [
                        {"ticker": "VWRL.L", "units": 10, "cost_basis_gbp": 900.0, "acquired_date": "2020-01-01"},
                        {"ticker": "AAPL.N", "units": 2, "cost_basis_gbp": 250.0, "acquired_date": "2020-01-01"},
                        {"ticker": "GSK.L", "units": 4, "cost_basis_gbp": 50.0, "acquired_date": "2020-01-01"},
                    ],
                }
            ],
        }
    ]
    with (
        patch("backend.common.portfolio_loader.list_portfolios", return_value=portfolios),
        patch(
            "backend.common.group_portfolio.data_loader.list_plots",
            return_value=[OwnerSummaryRecord(owner="alex")],
        ),
        patch("backend.common.group_portfolio.load_approvals", return_value={}),
        patch("backend.common.group_portfolio.load_user_config", return_value={}),
    ):
        result = gp.build_group_portfolio("all")

    holdings = {h["ticker"]: h for a in result["accounts"] for h in a["holdings"]}
    assert holdings["VWRL.L"]["price"] == pytest.approx(100.0)
    assert holdings["AAPL.N"]["price"] == pytest.approx(200.0 * 0.75)
    assert holdings["GSK.L"]["price"] == pytest.approx(15.0)
    assert holdings["VWRL.L"]["market_value_gbp"] == pytest.approx(1000.0)
    # Only the tickers priced from an earlier close are stale; GSK has a close
    # for the reporting date itself (#7919).
    assert holdings["VWRL.L"]["is_stale"] is True
    assert holdings["AAPL.N"]["is_stale"] is True
    assert holdings["GSK.L"]["is_stale"] is False
    assert sorted(refresh_queue.pending()) == [("AAPL", "N"), ("VWRL", "L")]


def _seed_usd_closes(cache, days: list[date]) -> None:
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(days),
            "Open": 100.0,
            "High": 100.0,
            "Low": 100.0,
            "Close": 100.0,
            "Volume": 1000,
            "Ticker": "AAPL",
            "Source": "Yahoo",
        }
    )
    path = cache.meta_timeseries_cache_path("AAPL", "N")
    cache._ensure_local_dir(path)
    frame.to_parquet(path, index=False)


def test_cache_only_fx_carries_a_rate_at_most_the_gap_window_and_never_backward(cache, no_live_calls):
    """A weekend takes Friday's rate; a date before the first stored rate, or past the window, has none (#9759)."""
    fri = date(2024, 3, 8)
    sat, mon = fri + timedelta(days=1), fri + timedelta(days=3)
    before = fri - timedelta(days=30)
    edge = mon + timedelta(days=cache._MAX_FX_GAP_FILL_DAYS)  # Sat 16 Mar: exactly 5 days after Monday
    stale = edge + timedelta(days=1)
    _seed_usd_closes(cache, [before, fri, sat, mon, edge, stale])
    frame = pd.DataFrame({"Date": pd.to_datetime([fri, mon]), "Rate": [0.7, 0.9]})
    path = cache._fx_cache_path("USD")
    cache._ensure_local_dir(path)
    frame.to_parquet(path, index=False)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("AAPL", "N", start_date=before, end_date=stale)

    by_day = dict(zip(df["Date"].dt.date, df["Close_gbp"]))
    assert by_day[fri] == pytest.approx(70.0)
    assert by_day[sat] == pytest.approx(70.0)
    assert by_day[mon] == pytest.approx(90.0)
    assert by_day[edge] == pytest.approx(90.0)
    assert pd.isna(by_day[before])  # no backfill from the first stored rate
    assert pd.isna(by_day[stale])  # six days old: not applied
    assert df["Close"].tolist() == [100.0] * 6  # native closes untouched


def test_cache_only_fx_rows_cover_the_gap_window_before_start(cache, no_live_calls):
    """The cache-only reader hands back stored rows from the window before ``start``, not a daily grid."""
    fri = date(2024, 3, 8)
    frame = pd.DataFrame({"Date": pd.to_datetime([fri - timedelta(days=7), fri]), "Rate": [0.6, 0.7]})
    path = cache._fx_cache_path("USD")
    cache._ensure_local_dir(path)
    frame.to_parquet(path, index=False)

    rows = cache._cached_fx_rates("USD", fri + timedelta(days=1), fri + timedelta(days=1), ticker="AAPL", exchange="N")

    assert rows["Date"].dt.date.tolist() == [fri]
    assert rows["Rate"].tolist() == [pytest.approx(0.7)]


def test_cache_only_gbp_instrument_in_another_base_currency_makes_no_live_calls(cache, no_live_calls, monkeypatch):
    """The GBP leg of a cross-currency conversion is the unit rate, never a fetch."""
    monkeypatch.setattr(cache, "fetch_fx_rate_range", _explode("fetch_fx_rate_range"))
    day = _target(cache)
    _seed_meta(cache, "GSK", "L", day, close=17.0)
    _seed_fx(cache, "EUR", day, rate=0.85)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("GSK", "L", start_date=day, end_date=day, base_currency="EUR")

    assert df["Close_eur"].tolist() == [pytest.approx(17.0 / 0.85)]
    assert refresh_queue.pending() == []


def test_cache_only_historical_read_does_not_queue(cache, no_live_calls):
    """Only reads that want the latest close queue a refresh of a stale ticker."""
    last = _weekday_back(_target(cache), 3)
    _seed_meta(cache, "ABC", "L", last)
    old = _weekday_back(last, 20)

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("ABC", "L", start_date=old, end_date=old)

    assert df["Date"].dt.date.tolist() == [old]
    assert refresh_queue.pending() == []


def test_refresh_fx_cache_for_tickers_refreshes_each_foreign_currency_live(cache, monkeypatch):
    """The scheduled refresh (refresh_prices) seeds the FX cache Lambda page requests read."""
    fetched = []

    def fake_live(base, quote, start, end):
        fetched.append(base)
        return pd.DataFrame({"Date": pd.bdate_range(end - timedelta(days=7), end).date, "Rate": 0.8})

    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", fake_live)
    # Only the held currencies here; the always-refreshed reference currencies
    # are covered in test_fx_history_store.py.
    monkeypatch.setattr(cache.config, "fx_reference_currencies", [])

    cache.refresh_fx_cache_for_tickers(["AAPL.N", "KO.N", "GSK.L", "CASH"])

    assert fetched == ["USD"]
    assert not cache._read_fx_parquet(cache._fx_cache_path("USD")).empty

    monkeypatch.setattr(cache.config, "offline_mode", True)
    cache.refresh_fx_cache_for_tickers(["AAPL.N"])
    assert fetched == ["USD"]


def test_lambda_skip_is_logged_once(cache, monkeypatch, caplog):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "allotmint-backend")
    monkeypatch.setattr(refresh_queue, "_lambda_skip_logged", False)

    with caplog.at_level("INFO", logger=refresh_queue.__name__):
        refresh_queue.enqueue("ABC", "L")
        refresh_queue.enqueue("DEF", "L")

    assert sum("PriceRefreshLambda" in r.getMessage() for r in caplog.records) == 1


def test_refresh_fx_cache_for_tickers_continues_past_a_failing_currency(cache, monkeypatch, caplog):
    """One currency's failed refresh is logged and doesn't stop the others (or refresh_prices)."""
    monkeypatch.setattr(cache, "get_instrument_meta", lambda full: {"currency": full.rsplit(".", 1)[1]})
    monkeypatch.setattr(cache.config, "fx_reference_currencies", [])
    refreshed = []

    def flaky(curr):
        if curr == "EUR":
            raise OSError("s3 unavailable")
        refreshed.append(curr)
        return True

    monkeypatch.setattr(cache, "refresh_fx_cache", flaky)

    with caplog.at_level("WARNING"):
        cache.refresh_fx_cache_for_tickers(["SAP.EUR", "AAPL.USD"])

    assert refreshed == ["USD"]
    assert any("FX cache refresh failed for EUR" in r.getMessage() for r in caplog.records)
