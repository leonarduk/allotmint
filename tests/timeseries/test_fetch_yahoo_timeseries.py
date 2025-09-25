from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from backend.timeseries.fetch_yahoo_timeseries import (
    _build_full_ticker,
    fetch_yahoo_timeseries_period,
    fetch_yahoo_timeseries_range,
    get_yahoo_suffix,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


@pytest.mark.parametrize(
    "exchange,suffix",
    [
        ("LSE", ".L"),
        ("l", ".L"),
        ("NASDAQ", ""),
        ("xetra", ".DE"),
        ("FX", "=X"),
    ],
)
def test_get_yahoo_suffix(exchange, suffix):
    assert get_yahoo_suffix(exchange) == suffix


def test_get_yahoo_suffix_unsupported():
    with pytest.raises(ValueError):
        get_yahoo_suffix("MOON")


def test_build_full_ticker_appends_suffix():
    assert _build_full_ticker("xdev", "l") == "XDEV.L"
    assert _build_full_ticker("PFE", "NASDAQ") == "PFE"


def test_build_full_ticker_no_duplicate():
    assert _build_full_ticker("XDEV.L", "L") == "XDEV.L"


def test_build_full_ticker_unsupported_exchange():
    with pytest.raises(ValueError):
        _build_full_ticker("TEST", "MOON")


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_range_normalizes(mock_ticker_cls):
    mock_stock = Mock()
    raw = pd.DataFrame(
        {
            "Open": [1.123],
            "High": [2.345],
            "Low": [0.567],
            "Close": [1.891],
            "Volume": [100],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )
    raw.index.name = "Date"
    mock_stock.history.return_value = raw
    mock_ticker_cls.return_value = mock_stock
    with patch(
        "backend.timeseries.fetch_yahoo_timeseries.is_valid_ticker",
        return_value=True,
    ):
        df = fetch_yahoo_timeseries_range(
            "abc", "l", start_date=date(2024, 1, 1), end_date=date(2024, 1, 1)
        )
    assert list(df.columns) == STANDARD_COLUMNS
    assert df.loc[0, "Date"] == date(2024, 1, 1)
    assert df.loc[0, "Open"] == 1.12
    assert df.loc[0, "High"] == 2.35
    assert df.loc[0, "Ticker"] == "ABC.L"
    assert df.loc[0, "Source"] == "Yahoo"


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_range_empty(mock_ticker_cls):
    mock_stock = Mock()
    mock_stock.history.return_value = pd.DataFrame()
    mock_ticker_cls.return_value = mock_stock
    with patch(
        "backend.timeseries.fetch_yahoo_timeseries.is_valid_ticker",
        return_value=True,
    ):
        with pytest.raises(ValueError):
            fetch_yahoo_timeseries_range(
                "abc", "l", start_date=date(2024, 1, 1), end_date=date(2024, 1, 2)
            )


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_range_exception(mock_ticker_cls):
    mock_stock = Mock()
    mock_stock.history.side_effect = Exception("boom")
    mock_ticker_cls.return_value = mock_stock
    with patch(
        "backend.timeseries.fetch_yahoo_timeseries.is_valid_ticker",
        return_value=True,
    ):
        with pytest.raises(Exception):
            fetch_yahoo_timeseries_range(
                "abc", "l", start_date=date(2024, 1, 1), end_date=date(2024, 1, 2)
            )


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_period_success(mock_ticker_cls):
    mock_stock = Mock()
    raw = pd.DataFrame(
        {
            "Open": [1.23],
            "High": [2.34],
            "Low": [1.11],
            "Close": [2.22],
            "Volume": [50],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )
    raw.index.name = "Date"
    mock_stock.history.return_value = raw
    mock_ticker_cls.return_value = mock_stock
    df = fetch_yahoo_timeseries_period("abc", "l", period="1mo", interval="1d")
    assert df.loc[0, "Ticker"] == "ABC.L"
    assert df.loc[0, "Date"] == date(2024, 1, 1)
    assert df.loc[0, "Source"] == "Yahoo"


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_period_no_normalize_preserves_datetime(mock_ticker_cls):
    mock_stock = Mock()
    raw = pd.DataFrame(
        {
            "Open": [1.23],
            "High": [2.34],
            "Low": [1.11],
            "Close": [2.22],
            "Volume": [50],
        },
        index=pd.to_datetime(["2024-01-01 10:30:00"]),
    )
    raw.index.name = "Datetime"
    mock_stock.history.return_value = raw
    mock_ticker_cls.return_value = mock_stock
    df = fetch_yahoo_timeseries_period(
        "abc", "l", period="5d", interval="5m", normalize=False
    )
    assert df.loc[0, "Date"] == pd.Timestamp("2024-01-01 10:30:00")


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_period_empty(mock_ticker_cls):
    mock_stock = Mock()
    mock_stock.history.return_value = pd.DataFrame()
    mock_ticker_cls.return_value = mock_stock
    with pytest.raises(ValueError):
        fetch_yahoo_timeseries_period("abc", "l", period="1mo", interval="1d")


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_fetch_yahoo_timeseries_period_exception(mock_ticker_cls):
    mock_stock = Mock()
    mock_stock.history.side_effect = Exception("boom")
    mock_ticker_cls.return_value = mock_stock
    with pytest.raises(Exception):
        fetch_yahoo_timeseries_period("abc", "l", period="1mo", interval="1d")

