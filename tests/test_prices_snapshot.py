import pandas as pd
from datetime import date, timedelta
import pytest

from backend.common import prices


def test_get_price_snapshot(monkeypatch):
    ticker = "ABC.L"
    yday = date.today() - timedelta(days=1)
    d7 = prices._nearest_weekday(yday - timedelta(days=7), forward=False)
    d30 = prices._nearest_weekday(yday - timedelta(days=30), forward=False)

    # Patch load_latest_prices to return a last price of 100
    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 100.0})

    # Map requested dates to fake close prices
    price_map = {d7: 90.0, d30: 80.0}

    def fake_load_meta_timeseries_range(sym, exch, start_date, end_date):
        val = price_map.get(start_date, 100.0)
        return pd.DataFrame({"close": [val]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load_meta_timeseries_range)

    snap = prices.get_price_snapshot([ticker])
    info = snap[ticker]

    assert info["last_price"] == 100.0
    assert info["last_price_date"] == yday.isoformat()
    assert info["change_7d_pct"] == pytest.approx((100 / 90.0 - 1) * 100)
    assert info["change_30d_pct"] == pytest.approx((100 / 80.0 - 1) * 100)
