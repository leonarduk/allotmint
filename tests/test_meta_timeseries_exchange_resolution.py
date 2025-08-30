import pandas as pd
from datetime import date

from backend.timeseries import fetch_meta_timeseries


def test_fetch_meta_timeseries_resolves_exchange_from_metadata(monkeypatch):
    calls = []

    def fake_yahoo(ticker, exchange, start_date, end_date):
        calls.append((ticker, exchange))
        return pd.DataFrame(
            {
                "Date": [start_date, end_date],
                "Open": [1.0, 1.0],
                "High": [1.0, 1.0],
                "Low": [1.0, 1.0],
                "Close": [1.0, 1.0],
                "Volume": [0, 0],
                "Ticker": [f"{ticker}.{exchange}", f"{ticker}.{exchange}"],
                "Source": ["Yahoo", "Yahoo"],
            }
        )

    monkeypatch.setattr(fetch_meta_timeseries, "fetch_yahoo_timeseries_range", fake_yahoo)
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_stooq_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_alphavantage_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_ft_timeseries", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "_is_isin", lambda ticker: False)
    monkeypatch.setattr(fetch_meta_timeseries, "is_valid_ticker", lambda *a, **k: True)

    df = fetch_meta_timeseries.fetch_meta_timeseries("GSK", start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))

    assert calls == [("GSK", "L")]
    assert not df.empty
