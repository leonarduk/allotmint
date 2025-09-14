import json
from datetime import date, timedelta, datetime, timezone

import pandas as pd
import pytest

from backend.common import prices


def test_close_on_returns_price(monkeypatch):
    df = pd.DataFrame({"close": [123.0]})
    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: d)
    monkeypatch.setattr(
        prices, "load_meta_timeseries_range", lambda *args, **kwargs: df
    )
    assert prices._close_on("ABC", "L", date.today()) == 123.0


def test_close_on_missing_columns(monkeypatch):
    df = pd.DataFrame({"foo": [1.0]})
    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: d)
    monkeypatch.setattr(
        prices, "load_meta_timeseries_range", lambda *args, **kwargs: df
    )
    assert prices._close_on("ABC", "L", date.today()) is None


def test_close_on_empty_df(monkeypatch):
    df = pd.DataFrame()
    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: d)
    monkeypatch.setattr(
        prices, "load_meta_timeseries_range", lambda *args, **kwargs: df
    )
    assert prices._close_on("ABC", "L", date.today()) is None


def test_close_on_invalid_value(monkeypatch):
    df = pd.DataFrame({"close": ["bad"]})
    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: d)
    monkeypatch.setattr(
        prices, "load_meta_timeseries_range", lambda *args, **kwargs: df
    )
    assert prices._close_on("ABC", "L", date.today()) is None


def test_get_price_snapshot_calculates_changes(monkeypatch):
    ticker = "ABC.L"
    last_price = 100.0
    yday = date.today() - timedelta(days=1)
    d7 = prices._nearest_weekday(yday - timedelta(days=7), forward=False)
    d30 = prices._nearest_weekday(yday - timedelta(days=30), forward=False)

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: last_price})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None
    )

    price_map = {d7: 90.0, d30: 80.0}

    def fake_load_meta_timeseries_range(sym, exch, start_date, end_date):
        return pd.DataFrame({"close": [price_map.get(start_date, last_price)]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load_meta_timeseries_range)

    snap = prices.get_price_snapshot([ticker])
    info = snap[ticker]
    assert info["last_price"] == last_price
    assert info["last_price_date"] == yday.isoformat()
    assert info["change_7d_pct"] == pytest.approx((last_price / 90.0 - 1) * 100)
    assert info["change_30d_pct"] == pytest.approx((last_price / 80.0 - 1) * 100)


def test_refresh_prices_writes_json_and_updates_cache(tmp_path, monkeypatch):
    ticker = "ABC.L"
    last_price = 100.0
    yday = date.today() - timedelta(days=1)
    d7 = prices._nearest_weekday(yday - timedelta(days=7), forward=False)
    d30 = prices._nearest_weekday(yday - timedelta(days=30), forward=False)

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [ticker])
    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: last_price})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None
    )

    price_map = {d7: 90.0, d30: 80.0}

    def fake_load_meta_timeseries_range(sym, exch, start_date, end_date):
        return pd.DataFrame({"close": [price_map.get(start_date, last_price)]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load_meta_timeseries_range)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", lambda snapshot: None)
    monkeypatch.setattr(prices, "check_price_alerts", lambda: None)

    out_path = tmp_path / "prices.json"
    monkeypatch.setattr(prices.config, "prices_json", out_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    result = prices.refresh_prices()

    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data == result["snapshot"]
    info = data[ticker]
    assert info["last_price"] == last_price
    assert info["change_7d_pct"] == pytest.approx((last_price / 90.0 - 1) * 100)
    assert info["change_30d_pct"] == pytest.approx((last_price / 80.0 - 1) * 100)
    assert prices.get_price_gbp(ticker) == last_price


def test_get_price_snapshot_resolved(monkeypatch):
    ticker = "ABC.L"
    last_price = 50.0
    yday = date.today() - timedelta(days=1)
    d7 = prices._nearest_weekday(yday - timedelta(days=7), forward=False)
    d30 = prices._nearest_weekday(yday - timedelta(days=30), forward=False)
    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: last_price})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("ABC", "L")
    )
    price_map = {d7: 40.0, d30: 30.0}

    def fake_load_meta_timeseries_range(sym, exch, start_date, end_date):
        assert sym == "ABC"
        assert exch == "L"
        return pd.DataFrame({"close": [price_map.get(start_date, last_price)]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load_meta_timeseries_range)
    snap = prices.get_price_snapshot([ticker])
    info = snap[ticker]
    assert info["last_price"] == last_price
    assert info["last_price_date"] == yday.isoformat()
    assert info["change_7d_pct"] == pytest.approx((last_price / 40.0 - 1) * 100)
    assert info["change_30d_pct"] == pytest.approx((last_price / 30.0 - 1) * 100)


def test_get_price_snapshot_live_data(monkeypatch):
    ticker = "ABC.L"
    now = datetime.now(timezone.utc)
    last_price = 110.0

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {ticker: {"price": last_price, "timestamp": now}})
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None
    )
    monkeypatch.setattr(
        prices, "load_meta_timeseries_range", lambda *a, **k: pd.DataFrame({"close": [100.0]})
    )

    snap = prices.get_price_snapshot([ticker])
    info = snap[ticker]
    assert info["last_price"] == last_price
    assert info["last_price_time"] == now.isoformat().replace("+00:00", "Z")
    assert info["is_stale"] is False


def test_refresh_prices_requires_config(monkeypatch):
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [])
    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {})
    monkeypatch.setattr(prices.config, "prices_json", None)
    with pytest.raises(RuntimeError):
        prices.refresh_prices()


def test_build_securities_from_portfolios(monkeypatch):
    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "XYZ", "name": "XYZ Plc"},
                        {"ticker": "abc"},
                        {"ticker": ""},
                    ]
                }
            ]
        }
    ]
    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)
    expected = {
        "XYZ": {"ticker": "XYZ", "name": "XYZ Plc"},
        "ABC": {"ticker": "ABC", "name": "ABC"},
    }
    assert prices._build_securities_from_portfolios() == expected


def test_get_security_meta(monkeypatch):
    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "XYZ", "name": "XYZ Plc"},
                    ]
                }
            ]
        }
    ]
    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)
    assert prices.get_security_meta("xyz") == {"ticker": "XYZ", "name": "XYZ Plc"}
