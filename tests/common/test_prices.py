"""Unit tests for :mod:`backend.common.prices`."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List

import pandas as pd
import pytest

from unittest.mock import Mock

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

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 118.5})
    monkeypatch.setattr(
        prices, "load_live_prices", lambda tickers: {ticker.upper(): {"price": 120.5, "timestamp": now}}
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("ABC", "L"))

    requested_dates: List[date] = []
    price_lookup = {seven_day: 100.0, thirty_day: 90.0}

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
    assert requested_dates == [seven_day, thirty_day]

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
    assert stale_info["change_7d_pct"] == pytest.approx((120.5 / 100.0 - 1.0) * 100.0)
    assert stale_info["change_30d_pct"] == pytest.approx((120.5 / 90.0 - 1.0) * 100.0)
    assert requested_dates == [seven_day, thirty_day]


def test_get_price_snapshot_handles_missing_live_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker_missing_price = "MNO.L"
    ticker_missing_ts = "PQR.L"
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)

    monkeypatch.setattr(
        prices,
        "_load_latest_prices",
        lambda tickers: {ticker_missing_price: 5.0, ticker_missing_ts: 6.0},
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

    missing_ts = snapshot[ticker_missing_ts]
    assert missing_ts["last_price"] == pytest.approx(1.0)
    assert missing_ts["last_price_time"] is None
    assert missing_ts["is_stale"] is True
    assert missing_ts["change_7d_pct"] is None
    assert missing_ts["change_30d_pct"] is None
    assert missing_ts["last_price_date"] == last_trading_day.isoformat()


def test_get_price_snapshot_defaults_to_cached_close(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "XYZ.L"
    base = ticker.split(".", 1)[0]
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    seven_day = last_trading_day - timedelta(days=7)
    thirty_day = last_trading_day - timedelta(days=30)

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 99.5})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None)

    requested: List[tuple[str, str, date]] = []

    def fake_close_on(sym: str, exch: str, requested_date: date) -> float | None:
        requested.append((sym, exch, requested_date))
        if requested_date == seven_day:
            return 88.0
        if requested_date == thirty_day:
            return None
        raise AssertionError(f"Unexpected date requested: {requested_date}")

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot([ticker])
    info = snapshot[ticker]

    assert info["last_price"] == pytest.approx(99.5)
    assert info["price_currency"] == "GBP"
    assert info["last_price_date"] == last_trading_day.isoformat()
    assert info["last_price_time"] is None
    assert info["is_stale"] is True
    assert info["change_7d_pct"] == pytest.approx((99.5 / 88.0 - 1.0) * 100.0)
    assert info["change_30d_pct"] is None
    assert requested == [
        (base, "L", seven_day),
        (base, "L", thirty_day),
    ]


def test_get_price_snapshot_uses_prior_weekday_on_weekend(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "WEEK.L"
    frozen_today = date(2024, 3, 24)  # Sunday
    expected_last_trading_day = prices._nearest_weekday(frozen_today - timedelta(days=1), forward=False)
    expected_7d_anchor = expected_last_trading_day - timedelta(days=7)
    expected_30d_anchor = expected_last_trading_day - timedelta(days=30)

    class FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen_today

    monkeypatch.setattr(prices, "date", FakeDate)
    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 111.0})
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
    assert requested_dates == [expected_7d_anchor, expected_30d_anchor]


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

    with caplog.at_level("DEBUG", logger="prices"):
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

    with caplog.at_level("WARNING", logger="prices"):
        frame = prices.load_prices_for_tickers(tickers)

    assert list(frame["Ticker"]) == ["AAA.L", "CCC.L"]
    assert "Failed to fetch prices for BBB.L" in caplog.text


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
        "ABC": {"ticker": "ABC", "name": "Alpha"},
        "DEF": {"ticker": "DEF", "name": "DEF"},
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


def test_refresh_prices_skips_write_when_all_prices_null(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Offline/no-data refresh must not overwrite a valid seed file with all-null prices."""
    seed = {"VWRL.L": {"last_price": 97.5, "price_currency": "GBP"}}
    output_path = tmp_path / "prices.json"
    output_path.write_text(json.dumps(seed))

    null_snapshot = {
        "VWRL.L": {"last_price": None, "price_currency": None, "is_stale": True}
    }
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["VWRL.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: null_snapshot)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", Mock())
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    prices.refresh_prices()

    assert json.loads(output_path.read_text()) == seed, (
        "Seed file must not be overwritten when every fetched price is None"
    )


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

    null_snapshot = {
        "VWRL.L": {"last_price": None, "price_currency": None, "is_stale": True}
    }
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


def test_refresh_prices_partial_null_preserves_existing_prices(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert result["AAA.L"]["last_price"] == pytest.approx(11.5), (
        "Successfully-fetched price must be updated"
    )
    assert result["BBB.L"]["last_price"] == pytest.approx(20.0), (
        "Seed price for null-returning ticker must be preserved"
    )

    assert len(in_memory_calls) == 1, "refresh_snapshot_in_memory must be called once"
    in_mem = in_memory_calls[0]
    assert in_mem["AAA.L"]["last_price"] == pytest.approx(11.5), (
        "In-memory snapshot must contain updated price"
    )
    assert in_mem["BBB.L"]["last_price"] == pytest.approx(20.0), (
        "In-memory snapshot must contain preserved seed price, not None"
    )
    assert price_cache.get("BBB.L") == pytest.approx(20.0), (
        "_price_cache must contain preserved seed price for null-returning ticker"
    )
