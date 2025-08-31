import datetime as dt

import pandas as pd
import pytest

from backend.timeseries import cache


def _sample_df(start: dt.date, end: dt.date):
    dates = pd.bdate_range(start, end)
    n = len(dates)
    base = list(range(1, n + 1))
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": base,
            "High": base,
            "Low": base,
            "Close": base,
            "Volume": [0] * n,
            "Ticker": ["T"] * n,
            "Source": ["test"] * n,
        }
    )


@pytest.mark.parametrize("exchange,rate", [("N", 0.8), ("DE", 0.9), ("CA", 0.6), ("TO", 0.6)])
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
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    df = cache.load_meta_timeseries_range("T", exchange, start, end)
    expected = [1 * rate, 2 * rate]
    for col in ["Open_gbp", "High_gbp", "Low_gbp", "Close_gbp"]:
        assert col in df.columns
        assert list(df[col].astype(float)) == pytest.approx(expected)
    for col in ["Open", "High", "Low", "Close"]:
        assert col in df.columns
        assert list(df[col].astype(float)) == [1.0, 2.0]


def test_missing_fx_rates_are_filled(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 3)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": ["0.8", None, "0.81"]})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    df = cache.load_meta_timeseries_range("T", "N", start, end)
    expected = [1 * 0.8, 2 * 0.8, 3 * 0.81]
    for col in ["Open_gbp", "High_gbp", "Low_gbp", "Close_gbp"]:
        assert col in df.columns
        assert list(df[col].astype(float)) == pytest.approx(expected)
    for col in ["Open", "High", "Low", "Close"]:
        assert col in df.columns
        assert list(df[col].astype(float)) == [1.0, 2.0, 3.0]


def test_string_fx_rates_are_converted(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": ["0.8", "0.81"]})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    df = cache.load_meta_timeseries_range("T", "N", start, end)
    expected = [1 * 0.8, 2 * 0.81]
    for col in ["Open_gbp", "High_gbp", "Low_gbp", "Close_gbp"]:
        assert col in df.columns
        assert list(df[col].astype(float)) == pytest.approx(expected)
    for col in ["Open", "High", "Low", "Close"]:
        assert col in df.columns
        assert list(df[col].astype(float)) == [1.0, 2.0]


def test_non_gbp_instrument_on_gbp_exchange(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": [1.25] * len(dates)})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(cache, "get_instrument_meta", lambda t: {"currency": "USD"})
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    df = cache.load_meta_timeseries_range("T", "L", start, end)
    assert list(df["Close"].astype(float)) == [1.0, 2.0]
    assert list(df["Close_gbp"].astype(float)) == [pytest.approx(1 * 1.25), pytest.approx(2 * 1.25)]


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
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

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
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    cache._memoized_range_cached.cache_clear()

    first = cache._memoized_range("T", "L", start.isoformat(), end.isoformat())
    first.loc[0, "Close"] = 999

    second = cache._memoized_range("T", "L", start.isoformat(), end.isoformat())
    assert calls["n"] == 1
    assert list(second["Close"]) == [1, 2]


def test_memoized_range_offline_no_cache_returns_empty(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    calls = {"n": 0}

    def fake_load_meta_timeseries(ticker, exchange, days_span):
        calls["n"] += 1
        return cache._empty_ts()

    monkeypatch.setattr(cache, "load_meta_timeseries", fake_load_meta_timeseries)
    monkeypatch.setattr(cache, "_load_parquet", lambda path: cache._empty_ts())
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    cache._memoized_range_cached.cache_clear()

    df = cache._memoized_range("T", "L", start.isoformat(), end.isoformat())
    assert df.empty
    assert calls["n"] == 1

def test_offline_mode_uses_fx_cache(tmp_path, monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "get_instrument_meta", lambda t: {"currency": "USD"})

    fx_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(pd.bdate_range(start, end)),
            "Rate": [0.8, 0.81],
        }
    )
    fx_path = tmp_path / "fx" / "USD.parquet"
    fx_path.parent.mkdir(parents=True)
    fx_df.to_parquet(fx_path, index=False)

    df = cache.load_meta_timeseries_range("T", "N", start, end)
    assert list(df["Close_gbp"].astype(float)) == [
        pytest.approx(1 * 0.8),
        pytest.approx(2 * 0.81),
    ]


def test_offline_falls_back_to_live_loader(tmp_path, monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    sample = _sample_df(start, end)

    def fake_fetch_meta_timeseries(ticker, exchange, start_date, end_date):
        return sample

    # Simulate offline mode with no cached data
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    monkeypatch.setattr(cache.config, "offline_mode", True)
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "fetch_meta_timeseries", fake_fetch_meta_timeseries)
    monkeypatch.setattr(cache, "get_instrument_meta", lambda t: {"currency": "GBP"})
    cache._memoized_range_cached.cache_clear()
    cache._load_meta_timeseries_cached.cache_clear()

    df = cache.load_meta_timeseries_range("T", "L", start, end)
    assert list(df["Close"].astype(float)) == [1.0, 2.0]

def test_offline_mode_fetch_fallback(monkeypatch, tmp_path):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": [0.8] * len(dates)})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "get_instrument_meta", lambda t: {"currency": "USD"})

    df = cache.load_meta_timeseries_range("T", "N", start, end)
    assert list(df["Close_gbp"].astype(float)) == [
        pytest.approx(1 * 0.8),
        pytest.approx(2 * 0.8),
    ]
