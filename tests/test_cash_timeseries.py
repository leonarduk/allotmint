from datetime import date, timedelta
import logging

from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries


def test_cash_timeseries_constant_one():
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=10)
    df = fetch_meta_timeseries("CASH", "GBP", start_date=start, end_date=end)
    assert not df.empty
    assert (df["Close"] == 1.0).all()
    assert (df["Open"] == 1.0).all()
    assert (df["High"] == 1.0).all()
    assert (df["Low"] == 1.0).all()
    assert df["Source"].iloc[0] == "cash"
    assert df["Ticker"].iloc[0].upper() == "CASH.GBP"


def test_cash_ticker_no_skip_logged(caplog):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=10)
    with caplog.at_level(logging.INFO):
        fetch_meta_timeseries("CASH", "GBP", start_date=start, end_date=end)
    assert "Skipping unrecognized ticker" not in caplog.text
