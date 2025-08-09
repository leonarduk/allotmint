import datetime as dt
import pandas as pd
import pytest
import yfinance as yf

from backend.utils.fx_rates import fetch_fx_rate_range


def _fake_df(start, end):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"Date": dates, "Close": [1.0 + i * 0.1 for i in range(len(dates))]})


def test_fetch_fx_rate_range_success(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 3)

    class FakeTicker:
        def history(self, start, end, interval):
            return _fake_df(start, end - dt.timedelta(days=1))

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range("USD", start, end)
    assert list(df["Date"]) == [dt.date(2024, 1, 1), dt.date(2024, 1, 2), dt.date(2024, 1, 3)]
    assert list(df["Rate"]) == [1.0, 1.1, 1.2]


def test_fetch_fx_rate_range_empty(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    class FakeTicker:
        def history(self, start, end, interval):
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range("USD", start, end)
    assert list(df["Rate"]) == [0.8, 0.8]


def test_fetch_fx_rate_range_exception(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 1)

    class FakeTicker:
        def history(self, start, end, interval):
            raise RuntimeError("boom")

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range("EUR", start, end)
    assert list(df["Rate"]) == [0.9]


def test_fetch_fx_rate_range_unsupported():
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 1)
    with pytest.raises(ValueError):
        fetch_fx_rate_range("JPY", start, end)
