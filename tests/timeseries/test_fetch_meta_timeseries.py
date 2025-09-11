from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


@pytest.mark.parametrize("ticker", ["", "   ", "BAD$"])
def test_invalid_or_blank_tickers_return_empty_df(ticker):
    df = fetch_meta_timeseries(ticker)
    assert df.empty
    assert list(df.columns) == STANDARD_COLUMNS


def _assert_cash_df(df, ticker, exchange, start, end):
    expected_dates = list(pd.bdate_range(start, end).date)
    assert df["Date"].tolist() == expected_dates
    assert (df[["Open", "High", "Low", "Close"]] == 1.0).all().all()
    assert (df["Volume"] == 0.0).all()
    assert (df["Ticker"] == f"{ticker}.{exchange}").all()
    assert (df["Source"] == "cash").all()


def test_cash_ticker_returns_constant_df():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    df = fetch_meta_timeseries("CASH", start_date=start, end_date=end)
    _assert_cash_df(df, "CASH", "", start, end)


def test_cash_exchange_returns_constant_df():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    df = fetch_meta_timeseries("USD", exchange="CASH", start_date=start, end_date=end)
    _assert_cash_df(df, "USD", "CASH", start, end)


@patch("backend.timeseries.fetch_meta_timeseries.record_skipped_ticker")
@patch("backend.timeseries.fetch_meta_timeseries.is_valid_ticker", return_value=False)
def test_invalid_ticker_records_skipped(mock_valid, mock_record):
    df = fetch_meta_timeseries("ABC", "L")
    assert df.empty
    mock_record.assert_called_once_with("ABC", "L", reason="unknown")


def test_yahoo_exception_triggers_stooq_fallback_and_min_coverage():
    start = date(2024, 1, 1)
    end = date(2024, 1, 5)

    stooq_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]).date,
            "Open": [1, 1, 1],
            "High": [1, 1, 1],
            "Low": [1, 1, 1],
            "Close": [1, 1, 1],
            "Volume": [0, 0, 0],
            "Ticker": ["ABC.L"] * 3,
            "Source": ["Stooq"] * 3,
        }
    )

    ft_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-04", "2024-01-05"]).date,
            "Open": [1, 1],
            "High": [1, 1],
            "Low": [1, 1],
            "Close": [1, 1],
            "Volume": [0, 0],
            "Ticker": ["ABC.L"] * 2,
            "Source": ["FT"] * 2,
        }
    )

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", side_effect=Exception("boom")), \
        patch.object(meta, "fetch_stooq_timeseries_range", return_value=stooq_df) as stooq_mock, \
        patch.object(meta, "fetch_ft_df", return_value=ft_df) as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries(
            "ABC", "L", start_date=start, end_date=end, min_coverage=1.0
        )

    stooq_mock.assert_called_once()
    ft_mock.assert_called_once()

    expected_dates = list(pd.bdate_range(start, end).date)
    assert df["Date"].tolist() == expected_dates
    assert set(df["Source"]) == {"Stooq", "FT"}
