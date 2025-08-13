import datetime as dt
import pandas as pd
import pytest

from backend.timeseries import cache


def _sample_df(start: dt.date, end: dt.date):
    dates = pd.bdate_range(start, end)
    n = len(dates)
    base = list(range(1, n + 1))
    return pd.DataFrame({
        "Date": pd.to_datetime(dates),
        "Open": base,
        "High": base,
        "Low": base,
        "Close": base,
        "Volume": [0] * n,
        "Ticker": ["T"] * n,
        "Source": ["test"] * n,
    })


@pytest.mark.parametrize("exchange,rate", [("N", 0.8), ("DE", 0.9), ("CA", 0.6)])
def test_prices_converted_to_gbp(monkeypatch, exchange, rate):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": [rate] * len(dates)})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)

    df = cache.load_meta_timeseries_range("T", exchange, start, end)
    closes = list(df["Close"].astype(float))
    assert closes == [pytest.approx(1 * rate), pytest.approx(2 * rate)]


def test_missing_fx_rates_are_filled(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 3)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": [0.8, None, 0.81]})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)

    df = cache.load_meta_timeseries_range("T", "N", start, end)
    closes = list(df["Close"].astype(float))
    assert closes == [
        pytest.approx(1 * 0.8),
        pytest.approx(2 * 0.8),
        pytest.approx(3 * 0.81),
    ]


def test_unsupported_currency_skips_conversion(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        raise ValueError("Unsupported currency")

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setitem(cache.EXCHANGE_TO_CCY, "ZZ", "XYZ")

    df = cache.load_meta_timeseries_range("T", "ZZ", start, end)
    assert df.empty


def test_memoized_range_returns_copy(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    sample = _sample_df(start, end)
    calls = {"n": 0}

    def fake_load_meta_timeseries(ticker, exchange, days_span):
        calls["n"] += 1
        return sample

    monkeypatch.setattr(cache, "load_meta_timeseries", fake_load_meta_timeseries)
    cache._memoized_range_cached.cache_clear()

    first = cache._memoized_range("T", "L", start.isoformat(), end.isoformat())
    first.loc[0, "Close"] = 999

    second = cache._memoized_range("T", "L", start.isoformat(), end.isoformat())
    assert calls["n"] == 1
    assert list(second["Close"]) == [1, 2]
