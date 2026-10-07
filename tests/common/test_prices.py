"""Unit tests for :mod:`backend.common.prices`."""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List
from unittest.mock import Mock

import pandas as pd
import pytest

from backend.common import prices


def test_close_on_returns_value_from_timeseries(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should read the GBP close from cached timeseries data."""

    queried: Dict[str, List] = {}
    sample_date = date(2024, 1, 2)
    frame = pd.DataFrame({"close_gbp": [101.23], "close": [99.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)

    def fake_load(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        queried["args"] = [sym, exch, start_date, end_date]
        return frame

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    result = prices._close_on("ABC", "L", sample_date)

    assert result == pytest.approx(101.23)
    assert queried["args"] == ["ABC", "L", sample_date, sample_date]


def test_close_on_handles_close_column_and_conversion_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_date = date(2024, 1, 5)

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)

    def fake_load_numeric(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        assert (sym, exch, start_date, end_date) == ("ABC", "L", sample_date, sample_date)
        return pd.DataFrame({"Close": ["101.50"]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load_numeric)

    assert prices._close_on("ABC", "L", sample_date) == pytest.approx(101.50)

    monkeypatch.setattr(
        prices,
        "load_meta_timeseries_range",
        lambda *args, **kwargs: pd.DataFrame({"Close": ["not-a-number"]}),
    )

    assert prices._close_on("ABC", "L", sample_date) is None


def test_get_price_snapshot_uses_latest_and_live(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "ABC.L"
    now = datetime.now(UTC)
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    seven_day = last_trading_day - timedelta(days=7)
    thirty_day = last_trading_day - timedelta(days=30)
    ninety_day = last_trading_day - timedelta(days=90)
    one_year = last_trading_day - timedelta(days=365)

    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {ticker: (118.5, last_trading_day)})
    monkeypatch.setattr(
        prices, "load_live_prices", lambda tickers: {ticker.upper(): {"price": 120.5, "timestamp": now}}
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("ABC", "L"))

    requested_dates: List[date] = []
    price_lookup = {seven_day: 100.0, thirty_day: 90.0, ninety_day: 80.0, one_year: 60.0}

    def fake_close_on(sym: str, exch: str, requested_date: date) -> float:
        requested_dates.append(requested_date)
        return price_lookup[requested_date]

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot([ticker])
    info = snapshot[ticker]

    assert info["last_price"] == pytest.approx(120.5)
    assert info["last_price_date"] == last_trading_day.isoformat()
    assert info["last_price_time"] == now.isoformat().replace("+00:00", "Z")
    assert info["is_stale"] is False
    assert info["change_7d_pct"] == pytest.approx((120.5 / 100.0 - 1.0) * 100.0)
    assert info["change_30d_pct"] == pytest.approx((120.5 / 90.0 - 1.0) * 100.0)
    assert info["change_90d_pct"] == pytest.approx((120.5 / 80.0 - 1.0) * 100.0)
    assert info["change_1y_pct"] == pytest.approx((120.5 / 60.0 - 1.0) * 100.0)
    assert requested_dates == [seven_day, thirty_day, ninety_day, one_year]

    requested_dates.clear()
    old_timestamp = now - timedelta(minutes=20)
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda tickers: {ticker.upper(): {"price": 120.5, "timestamp": old_timestamp}},
    )

    stale_snapshot = prices.get_price_snapshot([ticker])
    stale_info = stale_snapshot[ticker]

    assert stale_info["last_price"] == pytest.approx(120.5)
    assert stale_info["last_price_time"] == old_timestamp.isoformat().replace("+00:00", "Z")
    assert stale_info["is_stale"] is True
    # A stale live quote is still dated by the trading day its changes anchor to.
    assert stale_info["last_price_date"] == last_trading_day.isoformat()
    assert stale_info["change_7d_pct"] == pytest.approx((120.5 / 100.0 - 1.0) * 100.0)
    assert stale_info["change_30d_pct"] == pytest.approx((120.5 / 90.0 - 1.0) * 100.0)
    assert stale_info["change_1y_pct"] == pytest.approx((120.5 / 60.0 - 1.0) * 100.0)
    assert requested_dates == [seven_day, thirty_day, ninety_day, one_year]


def test_get_price_snapshot_handles_missing_live_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker_missing_price = "MNO.L"
    ticker_missing_ts = "PQR.L"
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)

    monkeypatch.setattr(
        prices,
        "_load_latest_closes",
        lambda tickers: {ticker_missing_price: (5.0, None), ticker_missing_ts: (6.0, None)},
    )
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda tickers: {
            ticker_missing_price.upper(): {"price": None, "timestamp": datetime.now(UTC)},
            ticker_missing_ts.upper(): {"price": 1.0, "timestamp": None},
        },
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("XYZ", "L"))
    monkeypatch.setattr(prices, "_close_on", lambda *args, **kwargs: 0)

    snapshot = prices.get_price_snapshot([ticker_missing_price, ticker_missing_ts])

    missing_price = snapshot[ticker_missing_price]
    assert missing_price["last_price"] is None
    assert missing_price["change_7d_pct"] is None
    assert missing_price["change_30d_pct"] is None
    assert missing_price["last_price_time"] is not None
    assert missing_price["last_price_date"] is None  # no price, so no price date

    missing_ts = snapshot[ticker_missing_ts]
    assert missing_ts["last_price"] == pytest.approx(1.0)
    assert missing_ts["last_price_time"] is None
    assert missing_ts["is_stale"] is True
    assert missing_ts["change_7d_pct"] is None
    assert missing_ts["change_30d_pct"] is None
    assert missing_ts["change_90d_pct"] is None
    assert missing_ts["change_1y_pct"] is None
    assert missing_ts["last_price_date"] == last_trading_day.isoformat()


def test_get_price_snapshot_defaults_to_cached_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """A close from the latest completed trading day, with no live quote, is fresh (#8595)."""
    ticker = "XYZ.L"
    base = ticker.split(".", 1)[0]
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    seven_day = last_trading_day - timedelta(days=7)
    thirty_day = last_trading_day - timedelta(days=30)

    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {ticker: (99.5, last_trading_day)})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None)

    requested: List[tuple[str, str, date]] = []

    def fake_close_on(sym: str, exch: str, requested_date: date) -> float | None:
        requested.append((sym, exch, requested_date))
        if requested_date == seven_day:
            return 88.0
        if requested_date in (thirty_day, last_trading_day - timedelta(days=90)):
            return None
        if requested_date == last_trading_day - timedelta(days=365):
            return 66.0
        raise AssertionError(f"Unexpected date requested: {requested_date}")

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot([ticker])
    info = snapshot[ticker]

    assert info["last_price"] == pytest.approx(99.5)
    assert info["price_currency"] == "GBP"
    assert info["last_price_date"] == last_trading_day.isoformat()
    assert info["last_price_time"] is None
    assert info["is_stale"] is False
    assert info["change_7d_pct"] == pytest.approx((99.5 / 88.0 - 1.0) * 100.0)
    assert info["change_30d_pct"] is None
    assert info["change_90d_pct"] is None
    assert info["change_1y_pct"] == pytest.approx((99.5 / 66.0 - 1.0) * 100.0)
    assert requested == [
        (base, "L", seven_day),
        (base, "L", thirty_day),
        (base, "L", last_trading_day - timedelta(days=90)),
        (base, "L", last_trading_day - timedelta(days=365)),
    ]


@pytest.mark.parametrize("close_age_days", [1, 10])
def test_get_price_snapshot_marks_older_cached_close_stale(
    monkeypatch: pytest.MonkeyPatch, close_age_days: int
) -> None:
    """A close older than the latest trading day is stale and reports its own date (#8595)."""
    ticker = "OLD.L"
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    close_day = last_trading_day - timedelta(days=close_age_days)

    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {ticker: (50.0, close_day)})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("OLD", "L"))
    monkeypatch.setattr(prices, "_close_on", lambda *args, **kwargs: None)

    info = prices.get_price_snapshot([ticker])[ticker]

    assert info["last_price"] == pytest.approx(50.0)
    assert info["is_stale"] is True
    assert info["last_price_date"] == close_day.isoformat()


def test_get_price_snapshot_close_dated_after_trading_day_is_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """A feed whose clock runs ahead of ours: the close isn't older than the trading day, so fresh."""
    ticker = "AHEAD.L"
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    close_day = last_trading_day + timedelta(days=1)

    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {ticker: (50.0, close_day)})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("AHEAD", "L"))
    monkeypatch.setattr(prices, "_close_on", lambda *args, **kwargs: None)

    info = prices.get_price_snapshot([ticker])[ticker]

    assert info["is_stale"] is False
    assert info["last_price_date"] == close_day.isoformat()


def test_get_price_snapshot_marks_undated_cached_close_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    """A close whose row date can't be determined is treated as stale, not silently fresh."""
    ticker = "NODATE.L"

    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {ticker: (50.0, None)})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("NODATE", "L"))
    monkeypatch.setattr(prices, "_close_on", lambda *args, **kwargs: None)

    info = prices.get_price_snapshot([ticker])[ticker]

    assert info["is_stale"] is True
    assert info["last_price_date"] is None


def test_get_price_snapshot_no_data_has_no_price_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """With neither a live quote nor a cached close, no price date is implied."""
    ticker = "NONE.L"

    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})

    info = prices.get_price_snapshot([ticker])[ticker]

    assert info["last_price"] is None
    assert info["price_currency"] is None
    assert info["last_price_date"] is None
    assert info["is_stale"] is True


def test_get_price_snapshot_uses_prior_weekday_on_weekend(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "WEEK.L"
    frozen_today = date(2024, 3, 24)  # Sunday
    expected_last_trading_day = prices._nearest_weekday(frozen_today - timedelta(days=1), forward=False)
    expected_7d_anchor = expected_last_trading_day - timedelta(days=7)
    expected_30d_anchor = expected_last_trading_day - timedelta(days=30)
    expected_90d_anchor = expected_last_trading_day - timedelta(days=90)
    expected_1y_anchor = expected_last_trading_day - timedelta(days=365)

    class FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen_today

    monkeypatch.setattr(prices, "date", FakeDate)
    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {ticker: (111.0, expected_last_trading_day)})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("WEEK", "L"))

    requested_dates: List[date] = []

    def fake_close_on(sym: str, exch: str, requested_date: date) -> float:
        requested_dates.append(requested_date)
        return 111.0

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot([ticker])
    info = snapshot[ticker]

    assert info["last_price_date"] == expected_last_trading_day.isoformat()
    assert requested_dates == [expected_7d_anchor, expected_30d_anchor, expected_90d_anchor, expected_1y_anchor]


def test_load_latest_prices_defaults_to_l(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    ticker = "AAA.L"
    frozen_today = date(2024, 3, 6)

    class FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen_today

    monkeypatch.setattr(prices, "date", FakeDate)

    expected_start = frozen_today - timedelta(days=365)
    expected_end = frozen_today - timedelta(days=1)
    weekday_calls: list[tuple[date, bool]] = []

    def fake_weekday(day: date, forward: bool) -> date:
        weekday_calls.append((day, forward))
        return day

    monkeypatch.setattr(prices, "_nearest_weekday", fake_weekday)
    frame = pd.DataFrame({"close": [95.0, 105.0]})

    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, cache: None)

    def fake_load(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        assert (sym, exch) == ("AAA", "L")
        assert start_date == expected_start
        assert end_date == expected_end
        return frame

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    with caplog.at_level("DEBUG", logger="backend.common.prices"):
        result = prices.load_latest_prices([ticker])

    assert result == {ticker: pytest.approx(105.0)}
    assert "defaulting to L" in caplog.text
    assert weekday_calls == [
        (expected_start, False),
        (expected_end, False),
    ]


def test_load_prices_for_tickers_combines_frames(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    start = date(2024, 1, 1)
    end = date(2024, 1, 10)

    def fake_nearest(day: date, forward: bool = False) -> date:
        return end if forward else start

    monkeypatch.setattr(prices, "_nearest_weekday", fake_nearest)

    mapping = {
        "AAA.L": ("AAA", "L"),
        "BBB.L": ("BBB", "L"),
        "CCC.L": None,
    }
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, cache: mapping[full])

    def fake_load(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        assert (start_date, end_date) == (start, end)
        if sym == "AAA":
            return pd.DataFrame({"close": [1.0]})
        if sym == "BBB":
            raise RuntimeError("boom")
        if sym == "CCC":
            return pd.DataFrame({"close": [3.0]})
        raise AssertionError(sym)

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    tickers = ["AAA.L", "BBB.L", "CCC.L"]

    with caplog.at_level("WARNING", logger="backend.common.prices"):
        frame = prices.load_prices_for_tickers(tickers)

    assert list(frame["Ticker"]) == ["AAA.L", "CCC.L"]
    assert "Failed to fetch prices for BBB.L" in caplog.text


def test_load_prices_for_tickers_fetches_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: each ticker's load_meta_timeseries_range call must run
    concurrently, not one at a time (confirmed live: ~1s+/ticker of
    S3-backed I/O, ~6-12s sequential for a 10-ticker portfolio). Also checks
    that Executor.map still returns frames in input order despite the
    concurrent fetch, matching test_load_prices_for_tickers_combines_frames
    above."""

    start = date(2024, 1, 1)
    end = date(2024, 1, 10)
    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: end if forward else start)
    monkeypatch.setattr(
        prices.instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".", 1)[0], "L"),
    )

    tickers = [f"T{i}.L" for i in range(6)]
    SLEEP_SECONDS = 0.2

    def slow_load(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        time.sleep(SLEEP_SECONDS)
        return pd.DataFrame({"close": [1.0]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", slow_load)

    started = time.monotonic()
    frame = prices.load_prices_for_tickers(tickers)
    elapsed = time.monotonic() - started

    assert list(frame["Ticker"]) == tickers
    assert elapsed < len(tickers) * SLEEP_SECONDS * 0.75


def test_load_prices_for_tickers_workers_inherit_cache_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """#9383: the per-ticker fetch threads must honour the caller's cache_only()."""
    from backend.timeseries.cache import cache_only, is_cache_only

    monkeypatch.setattr(
        prices.instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".", 1)[0], "L"),
    )
    seen: List[bool] = []

    def record_load(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        seen.append(is_cache_only())
        return pd.DataFrame({"close": [1.0]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", record_load)

    with cache_only():
        prices.load_prices_for_tickers([f"T{i}.L" for i in range(6)])
    assert seen == [True] * 6


def test_build_securities_from_portfolios(monkeypatch: pytest.MonkeyPatch) -> None:
    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "abc", "name": "Alpha"},
                        {"ticker": "DEF"},
                        {"ticker": ""},
                        {"ticker": None},
                    ]
                }
            ]
        },
        {"accounts": []},
    ]
    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)

    result = prices._build_securities_from_portfolios()

    assert result == {
        "ABC": {"ticker": "ABC", "name": "Alpha", "instrument_type": None},
        "DEF": {"ticker": "DEF", "name": "DEF", "instrument_type": None},
    }


def test_refresh_prices_writes_json_and_updates_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "XYZ.L"
    snapshot = {
        ticker: {
            "last_price": 145.0,
            "change_7d_pct": 3.2,
            "change_30d_pct": 5.4,
            "last_price_date": "2024-04-01",
            "last_price_time": None,
            "is_stale": True,
        }
    }

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [ticker])

    def fake_get_price_snapshot(tickers):
        assert tickers == [ticker]
        return snapshot

    monkeypatch.setattr(prices, "get_price_snapshot", fake_get_price_snapshot)
    refresh_mock = Mock()
    alerts_mock = Mock()
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", refresh_mock)
    monkeypatch.setattr(prices, "check_price_alerts", alerts_mock)

    output_path = tmp_path / "prices.json"
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    result = prices.refresh_prices()

    assert json.loads(output_path.read_text()) == snapshot
    assert result["tickers"] == [ticker]
    assert result["snapshot"] == snapshot
    assert result["timestamp"].endswith("Z")
    assert prices._price_cache == {ticker.upper(): snapshot[ticker]["last_price"]}
    refresh_mock.assert_called_once_with(snapshot)
    alerts_mock.assert_called_once_with()


def test_refresh_prices_skips_write_when_all_prices_null(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline/no-data refresh must not overwrite a valid seed file with all-null prices."""
    seed = {"VWRL.L": {"last_price": 97.5, "price_currency": "GBP"}}
    output_path = tmp_path / "prices.json"
    output_path.write_text(json.dumps(seed))

    null_snapshot = {"VWRL.L": {"last_price": None, "price_currency": None, "is_stale": True}}
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["VWRL.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: null_snapshot)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    prices.refresh_prices()

    assert (
        json.loads(output_path.read_text()) == seed
    ), "Seed file must not be overwritten when every fetched price is None"


def test_refresh_prices_uploads_existing_snapshot_to_s3_when_all_prices_null(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when no fresh prices are fetched, the S3 key must always be (re)written.

    Otherwise a refresh that runs during a market-closed/offline window never
    creates ``prices/latest_prices.json`` in S3, and consumers that wait for
    that key (e.g. the deploy workflow's post-deploy snapshot check) hang
    indefinitely. See issue #3685.
    """
    seed = {"VWRL.L": {"last_price": 97.5, "price_currency": "GBP"}}
    output_path = tmp_path / "prices.json"
    output_path.write_text(json.dumps(seed))

    null_snapshot = {"VWRL.L": {"last_price": None, "price_currency": None, "is_stale": True}}
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["VWRL.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: null_snapshot)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})
    monkeypatch.setattr(prices.config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    put_calls = []

    class _FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda svc: _FakeS3()))

    prices.refresh_prices()

    assert len(put_calls) == 1
    assert put_calls[0]["Bucket"] == "test-bucket"
    assert put_calls[0]["Key"] == prices.PRICES_S3_KEY
    assert json.loads(put_calls[0]["Body"]) == seed
    assert put_calls[0]["ContentType"] == "application/json"


def test_refresh_universe_finds_held_tickers_with_auth_enabled_only_as_system_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through list_all_unique_tickers -> list_portfolios -> _list_aws_plots (#8805).

    With auth enabled and no request user, owner discovery hides every owner,
    so the refresh universe is empty -- unless it runs as a system job, as the
    scheduled PriceRefreshLambda does.
    """
    from backend.auth import system_job_context
    from backend.common import data_loader, portfolio_loader, portfolio_utils

    class _FakeS3Provider:
        def list_plots(self, current_user=None):
            return [{"owner": "alice", "accounts": ["isa"]}]

    monkeypatch.setattr(data_loader.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(data_loader.config, "app_env", "aws", raising=False)
    monkeypatch.setattr(data_loader, "S3DataProvider", _FakeS3Provider)
    monkeypatch.setattr(data_loader, "load_person_meta", lambda owner: {})
    monkeypatch.setattr(
        portfolio_loader,
        "_build_owner_portfolio",
        lambda summary: {"owner": summary.owner, "person": {}, "accounts": [{"holdings": [{"ticker": "AAA.L"}]}]},
    )
    monkeypatch.setattr(portfolio_utils, "list_virtual_portfolios", lambda: [])
    monkeypatch.setattr(prices.price_triggers, "watched_tickers", lambda: [])

    assert prices.refresh_universe() == []
    with system_job_context():
        assert prices.refresh_universe() == ["AAA.L"]


def _empty_refresh(
    tmp_path, monkeypatch: pytest.MonkeyPatch, *, snapshot_exists: bool, put_error: Exception | None = None
) -> list:
    """Run refresh_prices with nothing fetched and no local seed (a fresh Lambda container).

    The fake S3 honours ``IfNoneMatch="*"`` like the real one: 412 when the key exists.
    ``put_error``, when given, is raised by every ``put_object`` call instead.
    """
    from botocore.exceptions import ClientError

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [])
    monkeypatch.setattr(prices.price_triggers, "watched_tickers", lambda: [])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: {})
    monkeypatch.setattr(prices, "refresh_fx_cache_for_tickers", lambda _: None)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", tmp_path / "prices.json")
    monkeypatch.setattr(prices.config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    written: list = []

    def put_object(**kwargs):
        if put_error is not None:
            raise put_error
        if kwargs.get("IfNoneMatch") == "*" and snapshot_exists:
            raise ClientError({"Error": {"Code": "PreconditionFailed", "Message": "exists"}}, "PutObject")
        written.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "boto3", SimpleNamespace(client=lambda svc: SimpleNamespace(put_object=put_object))
    )

    prices.refresh_prices()
    return written


def test_refresh_prices_keeps_existing_s3_snapshot_when_nothing_fetched(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An empty refresh must not replace a good S3 snapshot with {} (#8805)."""
    with caplog.at_level("ERROR", logger=prices.logger.name):
        written = _empty_refresh(tmp_path, monkeypatch, snapshot_exists=True)

    assert written == []
    messages = [r.getMessage() for r in caplog.records]
    assert any("universe is empty" in m for m in messages)
    assert any("keeping the existing S3 price snapshot" in m for m in messages)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (None, True),  # key absent: written
        ("PreconditionFailed", False),  # 412: key exists, kept
        ("ConditionalRequestConflict", False),  # 409: a concurrent write won the race
    ],
)
def test_put_empty_snapshot_if_absent(code, expected) -> None:
    from botocore.exceptions import ClientError

    calls = []

    def put_object(**kwargs):
        calls.append(kwargs)
        if code:
            raise ClientError({"Error": {"Code": code, "Message": code}}, "PutObject")

    assert prices.put_empty_snapshot_if_absent(SimpleNamespace(put_object=put_object), "bucket") is expected
    assert calls[0]["IfNoneMatch"] == "*"
    assert calls[0]["Body"] == b"{}"


def test_put_empty_snapshot_if_absent_raises_other_errors() -> None:
    """Anything but 412/409 isn't "already exists", so it propagates to the caller's handler."""
    from botocore.exceptions import ClientError

    def put_object(**_kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject")

    with pytest.raises(ClientError):
        prices.put_empty_snapshot_if_absent(SimpleNamespace(put_object=put_object), "bucket")


def test_refresh_prices_seeds_missing_s3_snapshot_when_nothing_fetched(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no snapshot at all, {} is still written so the key exists (#3685) -- conditionally."""
    written = _empty_refresh(tmp_path, monkeypatch, snapshot_exists=False)

    assert len(written) == 1
    assert json.loads(written[0]["Body"]) == {}
    assert written[0]["IfNoneMatch"] == "*"


def test_refresh_prices_logs_error_when_missing_snapshot_cannot_be_seeded(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A denied conditional seed may leave the key missing (#3685), so it is an ERROR, not a WARNING (#8943)."""
    from botocore.exceptions import ClientError

    denied = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject")
    with caplog.at_level("WARNING", logger=prices.logger.name):
        written = _empty_refresh(tmp_path, monkeypatch, snapshot_exists=False, put_error=denied)

    assert written == []
    seed_failures = [r for r in caplog.records if "Failed to seed a missing S3 price snapshot" in r.getMessage()]
    assert [r.levelname for r in seed_failures] == ["ERROR"]
    assert not any(r.levelname == "WARNING" and "S3" in r.getMessage() for r in caplog.records)


def test_upload_snapshot_failure_with_prices_stays_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed non-empty overwrite leaves the previous snapshot in place, so it stays a WARNING."""

    def put_object(**_kwargs):
        raise OSError("connection reset")

    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setitem(
        sys.modules, "boto3", SimpleNamespace(client=lambda svc: SimpleNamespace(put_object=put_object))
    )

    with caplog.at_level("WARNING", logger=prices.logger.name):
        prices._upload_snapshot_to_s3({"AAA.L": {"last_price": 1.0}})

    assert [(r.levelname, r.getMessage().split(":")[0]) for r in caplog.records] == [
        ("WARNING", "Failed to upload price snapshot to S3")
    ]


def test_refresh_prices_partial_null_preserves_existing_prices(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Partial-outage refresh updates valid prices and preserves existing ones for null tickers."""
    seed = {
        "AAA.L": {"last_price": 10.0, "price_currency": "GBP"},
        "BBB.L": {"last_price": 20.0, "price_currency": "GBP"},
    }
    output_path = tmp_path / "prices.json"
    output_path.write_text(json.dumps(seed))

    partial_snapshot = {
        "AAA.L": {"last_price": 11.5, "price_currency": "GBP", "is_stale": False},
        "BBB.L": {"last_price": None, "price_currency": None, "is_stale": True},
    }
    in_memory_calls: list = []
    price_cache: dict = {}

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["AAA.L", "BBB.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: partial_snapshot)
    monkeypatch.setattr(
        prices,
        "refresh_snapshot_in_memory",
        lambda s: in_memory_calls.append(s),
    )
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", price_cache)

    prices.refresh_prices()

    result = json.loads(output_path.read_text())
    assert result["AAA.L"]["last_price"] == pytest.approx(11.5), "Successfully-fetched price must be updated"
    assert result["BBB.L"]["last_price"] == pytest.approx(
        20.0
    ), "Seed price for null-returning ticker must be preserved"

    assert len(in_memory_calls) == 1, "refresh_snapshot_in_memory must be called once"
    in_mem = in_memory_calls[0]
    assert in_mem["AAA.L"]["last_price"] == pytest.approx(11.5), "In-memory snapshot must contain updated price"
    assert in_mem["BBB.L"]["last_price"] == pytest.approx(
        20.0
    ), "In-memory snapshot must contain preserved seed price, not None"
    assert price_cache.get("BBB.L") == pytest.approx(
        20.0
    ), "_price_cache must contain preserved seed price for null-returning ticker"


def test_refresh_prices_reports_unpriced_tickers(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Tickers the refresh cannot price are logged and returned with a reason (#8595)."""
    snapshot = {
        "AAA.L": {"last_price": 11.5},
        "BBB.L": {"last_price": None},
        "CCC.L": {"last_price": 0.0},
    }
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["AAA.L", "BBB.L", "CCC.L", "DDD.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: snapshot)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    prices_json = tmp_path / "prices.json"
    prices_json.write_text(json.dumps({"BBB.L": {"last_price": 9.0, "last_price_date": "2026-09-01"}}))
    monkeypatch.setattr(prices.config, "prices_json", prices_json)
    monkeypatch.setattr(prices, "_price_cache", {})

    with caplog.at_level(logging.WARNING, logger=prices.logger.name):
        result = prices.refresh_prices()

    assert result["unpriced"] == {
        "BBB.L": "no price returned; keeping price from 2026-09-01",
        "CCC.L": "non-positive price 0.0; no previous price",
        "DDD.L": "missing from snapshot; no previous price",
    }
    assert "could not price 3 of 4 tickers" in caplog.text
    assert "BBB.L" in caplog.text and "AAA.L" not in caplog.text
    # The report is log/return-value only: prices.json keeps its ticker -> entry shape.
    persisted = json.loads(prices_json.read_text())
    assert set(persisted) == {"AAA.L", "BBB.L"}
    assert persisted["BBB.L"]["last_price"] == 9.0


def test_refresh_prices_reports_no_unpriced_when_all_priced(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Every ticker priced: ``unpriced`` is an empty dict and nothing is logged (#8595)."""
    snapshot = {"AAA.L": {"last_price": 11.5}, "BBB.L": {"last_price": 2.0}}
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["AAA.L", "BBB.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: snapshot)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", tmp_path / "prices.json")
    monkeypatch.setattr(prices, "_price_cache", {})

    with caplog.at_level(logging.WARNING, logger=prices.logger.name):
        result = prices.refresh_prices()

    assert result["unpriced"] == {}
    assert "could not price" not in caplog.text


def test_refresh_prices_filters_nan_zero_and_negative_prices(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end NaN/zero/negative guard: mock the underlying price fetches
    (``_load_latest_closes`` / ``load_live_prices``) so ``get_price_snapshot``
    runs for real, then verify ``refresh_prices``'s write-boundary filter
    keeps only finite, strictly-positive prices — preserving any existing
    seed value for tickers whose freshly-fetched price is NaN, zero, or
    negative."""

    tickers = ["NAN.L", "ZERO.L", "NEG.L", "OK.L"]
    seed = {
        "NAN.L": {"last_price": 10.0, "price_currency": "GBP"},
        "ZERO.L": {"last_price": 20.0, "price_currency": "GBP"},
        "NEG.L": {"last_price": 30.0, "price_currency": "GBP"},
    }
    output_path = tmp_path / "prices.json"
    output_path.write_text(json.dumps(seed))

    now = datetime.now(UTC)
    # Live prices supply a NaN and a negative price directly; last-close
    # fallback supplies a zero price for the ticker with no live entry.
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda t: {
            "NAN.L": {"price": float("nan"), "timestamp": now},
            "NEG.L": {"price": -5.0, "timestamp": now},
            "OK.L": {"price": 12.0, "timestamp": now},
        },
    )
    monkeypatch.setattr(
        prices,
        "_load_latest_closes",
        lambda t, **_kwargs: {"ZERO.L": (0.0, None)},
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None)
    monkeypatch.setattr(prices, "_close_on", lambda *a, **k: None)
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: tickers)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    result = prices.refresh_prices()

    snapshot = result["snapshot"]
    # get_price_snapshot's own NaN guard converts the NaN live price to None...
    assert snapshot["NAN.L"]["last_price"] is None
    # ...but zero and negative prices are not filtered at that layer, only
    # at refresh_prices's write-boundary filter.
    assert snapshot["ZERO.L"]["last_price"] == pytest.approx(0.0)
    assert snapshot["NEG.L"]["last_price"] == pytest.approx(-5.0)
    assert snapshot["OK.L"]["last_price"] == pytest.approx(12.0)

    written = json.loads(output_path.read_text())
    # NaN/zero/negative fetched prices must not overwrite the seed values.
    assert written["NAN.L"]["last_price"] == pytest.approx(10.0)
    assert written["ZERO.L"]["last_price"] == pytest.approx(20.0)
    assert written["NEG.L"]["last_price"] == pytest.approx(30.0)
    # A genuinely valid fresh price is persisted.
    assert written["OK.L"]["last_price"] == pytest.approx(12.0)


def test_refresh_prices_fetches_live_and_refreshes_fx_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scheduled refresh stays on the live path and seeds the FX cache (#7917).

    Page requests read prices and FX rates from cache only, so on Lambda this
    job is what keeps both current.
    """
    from backend.timeseries import cache

    tickers = ["AAPL.N", "XYZ.L"]
    seen: Dict[str, object] = {}

    def fake_get_price_snapshot(ts):
        seen["cache_only"] = cache.is_cache_only()
        return {}

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: tickers)
    monkeypatch.setattr(prices, "get_price_snapshot", fake_get_price_snapshot)
    monkeypatch.setattr(prices, "refresh_fx_cache_for_tickers", lambda ts: seen.setdefault("fx", list(ts)))
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", tmp_path / "prices.json")
    monkeypatch.setattr(prices, "_price_cache", {})

    prices.refresh_prices()

    assert seen == {"cache_only": False, "fx": tickers}


def test_refresh_prices_persists_snapshot_when_fx_refresh_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An FX cache refresh error is logged and doesn't block writing prices.json (#7917)."""
    ticker = "XYZ.L"
    snapshot = {ticker: {"last_price": 145.0, "last_price_date": "2024-04-01"}}

    def failing_fx(_tickers):
        raise RuntimeError("fx store unavailable")

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [ticker])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _ts: snapshot)
    monkeypatch.setattr(prices, "refresh_fx_cache_for_tickers", failing_fx)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    output_path = tmp_path / "prices.json"
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    prices.refresh_prices()

    assert json.loads(output_path.read_text()) == snapshot


def _stub_refresh(monkeypatch: pytest.MonkeyPatch, tmp_path, snapshot: Dict) -> None:
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: list(snapshot))
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _ts: snapshot)
    monkeypatch.setattr(prices, "refresh_fx_cache_for_tickers", lambda _ts: None)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", tmp_path / "prices.json")
    monkeypatch.setattr(prices, "_price_cache", {})


def test_refresh_prices_refreshes_boe_rates_when_online(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scheduled refresh keeps the stored Bank of England series current (#9322)."""
    calls = []
    _stub_refresh(monkeypatch, tmp_path, {})
    monkeypatch.setattr(prices, "refresh_boe_series", lambda: calls.append("boe") or {})
    monkeypatch.setattr(prices.config, "offline_mode", False)

    prices.refresh_prices()

    assert calls == ["boe"]


def test_refresh_prices_skips_boe_rates_offline(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_refresh(monkeypatch, tmp_path, {})
    monkeypatch.setattr(prices, "refresh_boe_series", lambda: pytest.fail("BoE fetched offline"))
    monkeypatch.setattr(prices.config, "offline_mode", True)

    prices.refresh_prices()


def test_refresh_prices_persists_snapshot_when_boe_refresh_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = {"XYZ.L": {"last_price": 145.0, "last_price_date": "2024-04-01"}}

    def failing_boe():
        raise ConnectionError("boe unreachable")

    _stub_refresh(monkeypatch, tmp_path, snapshot)
    monkeypatch.setattr(prices, "refresh_boe_series", failing_boe)
    monkeypatch.setattr(prices.config, "offline_mode", False)

    prices.refresh_prices()

    assert json.loads((tmp_path / "prices.json").read_text()) == snapshot
