from datetime import date, timedelta

import pandas as pd
import pytest

from backend.common import prices


def test_get_price_snapshot(monkeypatch):
    ticker = "ABC.L"
    frozen_today = date(2024, 4, 8)

    class FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen_today

    monkeypatch.setattr(prices, "date", FakeDate)

    weekday_calls: list[tuple[date, bool]] = []

    def fake_weekday(day: date, forward: bool) -> date:
        weekday_calls.append((day, forward))
        return day

    monkeypatch.setattr(prices, "_nearest_weekday", fake_weekday)

    last_trading_day = frozen_today - timedelta(days=1)
    d7 = last_trading_day - timedelta(days=7)
    d30 = last_trading_day - timedelta(days=30)

    # Patch load_latest_prices to return a last price of 100
    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 100.0})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})

    # Map requested dates to fake close prices
    price_map = {d7: 90.0, d30: 80.0}

    def fake_load_meta_timeseries_range(sym, exch, start_date, end_date):
        val = price_map.get(start_date, 100.0)
        return pd.DataFrame({"close": [val]})

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load_meta_timeseries_range)

    snap = prices.get_price_snapshot([ticker])
    info = snap[ticker]

    assert info["last_price"] == 100.0
    assert info["last_price_date"] == last_trading_day.isoformat()
    assert info["change_7d_pct"] == pytest.approx((100 / 90.0 - 1) * 100)
    assert info["change_30d_pct"] == pytest.approx((100 / 80.0 - 1) * 100)
    assert weekday_calls[0] == (frozen_today - timedelta(days=1), False)
    assert (last_trading_day - timedelta(days=7), False) in weekday_calls
    assert (last_trading_day - timedelta(days=30), False) in weekday_calls
