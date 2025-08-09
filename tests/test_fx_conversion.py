import datetime as dt
import pandas as pd
import pytest

from backend.timeseries import cache
from backend.utils import fx_rates


def _sample_df(start: dt.date, end: dt.date):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({
        "Date": pd.to_datetime(dates),
        "Open": [1.0, 2.0][:len(dates)],
        "High": [1.0, 2.0][:len(dates)],
        "Low": [1.0, 2.0][:len(dates)],
        "Close": [1.0, 2.0][:len(dates)],
        "Volume": [0, 0][:len(dates)],
        "Ticker": ["T"] * len(dates),
        "Source": ["test"] * len(dates),
    })


@pytest.mark.parametrize("exchange,rate", [("N", 0.8), ("DE", 0.9)])
def test_prices_converted_to_gbp(monkeypatch, exchange, rate):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    def fake_memoized_range(ticker, exch, s_iso, e_iso):
        return _sample_df(start, end)

    def fake_fx(base, s, e):
        dates = pd.bdate_range(s, e).date
        return pd.DataFrame({"Date": dates, "Rate": [rate] * len(dates)})

    monkeypatch.setattr(cache, "_memoized_range", fake_memoized_range)
    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range", fake_fx)

    df = cache.load_meta_timeseries_range("T", exchange, start, end)
    closes = list(df["Close"].astype(float))
    assert closes == [pytest.approx(1.0 * rate), pytest.approx(2.0 * rate)]
