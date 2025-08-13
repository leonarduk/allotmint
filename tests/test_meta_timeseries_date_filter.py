import pandas as pd
from datetime import date

from backend.timeseries import fetch_meta_timeseries


def test_fetch_meta_timeseries_handles_python_dates(monkeypatch):
    """fetch_meta_timeseries should handle date objects without TypeError."""
    # Make all primary sources return empty to force FT fallback
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_yahoo_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_stooq_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_alphavantage_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "_is_isin", lambda ticker: False)

    def fake_ft(ticker, days):
        return pd.DataFrame(
            {
                "Date": [date(2024, 1, 1), date(2024, 1, 3)],
                "Open": [1.0, 1.0],
                "High": [1.0, 1.0],
                "Low": [1.0, 1.0],
                "Close": [1.0, 1.0],
                "Volume": [0, 0],
                "Ticker": [ticker, ticker],
                "Source": ["FT", "FT"],
            }
        )

    monkeypatch.setattr(fetch_meta_timeseries, "fetch_ft_timeseries", fake_ft)

    df = fetch_meta_timeseries.fetch_meta_timeseries(
        "ABC", "L", start_date=date(2024, 1, 1), end_date=date(2024, 1, 2)
    )

    assert not df.empty
    assert pd.to_datetime(df["Date"]).max() <= pd.Timestamp(date(2024, 1, 2))
