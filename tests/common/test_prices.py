import json
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.common import prices


def test_get_price_snapshot_calculates_changes(monkeypatch):
    ticker = "ABC.L"
    last_price = 100.0
    yday = date.today() - timedelta(days=1)
    d7 = prices._nearest_weekday(yday - timedelta(days=7), forward=False)
    d30 = prices._nearest_weekday(yday - timedelta(days=30), forward=False)

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: last_price})

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
