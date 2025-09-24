from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from backend.timeseries.fetch_meta_timeseries import (
    _coverage_ratio,
    _merge,
    _resolve_exchange_from_metadata,
    _resolve_ticker_exchange,
    fetch_meta_timeseries,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


def test_resolve_exchange_from_metadata(tmp_path):
    instruments = tmp_path / "data" / "instruments" / "L"
    instruments.mkdir(parents=True)
    (instruments / "ABC.json").write_text("{}")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "INSTRUMENTS_DIR", tmp_path / "data" / "instruments"):
        assert meta._resolve_exchange_from_metadata("abc") == "L"
        assert meta._resolve_exchange_from_metadata("XYZ") == ""


def test_resolve_ticker_exchange_precedence():
    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "_resolve_exchange_from_metadata", return_value="Q"):
        # suffix beats exchange argument and metadata
        assert meta._resolve_ticker_exchange("ABC.L", "N") == ("ABC", "L")
        # argument beats metadata
        assert meta._resolve_ticker_exchange("ABC", "N") == ("ABC", "N")
        # metadata used when nothing else supplied
        assert meta._resolve_ticker_exchange("ABC", "") == ("ABC", "Q")


def test_merge_and_coverage_ratio():
    df1 = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]).date,
            "Open": [1, 2],
            "High": [1, 2],
            "Low": [1, 2],
            "Close": [1, 2],
            "Volume": [10, 20],
            "Ticker": ["ABC.L", "ABC.L"],
            "Source": ["A", "A"],
        }
    )

    df2 = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]).date,
            "Open": [2, 3],
            "High": [2, 3],
            "Low": [2, 3],
            "Close": [2, 3],
            "Volume": [20, 30],
            "Ticker": ["ABC.L", "ABC.L"],
            "Source": ["B", "B"],
        }
    )

    merged = _merge([df1, df2])
    assert merged["Date"].tolist() == list(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]).date)
    assert merged.iloc[1]["Source"] == "B"

    expected = set(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]).date)
    ratio = _coverage_ratio(merged, expected)
    assert ratio == pytest.approx(3 / 4)


def test_fetch_meta_timeseries_invalid_ticker():
    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "is_valid_ticker", return_value=False) as valid_mock, \
        patch.object(meta, "record_skipped_ticker") as record_mock, \
        patch.object(meta, "fetch_yahoo_timeseries_range") as yahoo_mock:
        df = meta.fetch_meta_timeseries("ABC", "L")

    assert df.empty
    yahoo_mock.assert_not_called()
    record_mock.assert_called_once_with("ABC", "L", reason="unknown")
    valid_mock.assert_called_once()


def _assert_cash_df(df, ticker, exchange, start, end):
    expected_dates = list(pd.bdate_range(start, end).date)
    assert df["Date"].tolist() == expected_dates
    assert (df[["Open", "High", "Low", "Close"]] == 1.0).all().all()
    assert (df["Volume"] == 0.0).all()
    assert (df["Ticker"] == f"{ticker}.{exchange}").all()
    assert (df["Source"] == "cash").all()


def test_fetch_meta_timeseries_cash_ticker():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    df = fetch_meta_timeseries("CASH", start_date=start, end_date=end)
    _assert_cash_df(df, "CASH", "", start, end)


def _make_df(dates, source, ticker="ABC.L"):
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates).date,
            "Open": [1] * len(dates),
            "High": [1] * len(dates),
            "Low": [1] * len(dates),
            "Close": [1] * len(dates),
            "Volume": [0] * len(dates),
            "Ticker": [ticker] * len(dates),
            "Source": [source] * len(dates),
        }
    )


def test_fetch_meta_timeseries_yahoo_only():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    yahoo_df = _make_df(["2024-01-01", "2024-01-02", "2024-01-03"], "Yahoo")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range") as stooq_mock, \
        patch.object(meta, "fetch_ft_df") as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    assert df.equals(yahoo_df)
    yahoo_mock.assert_called_once()
    stooq_mock.assert_not_called()
    ft_mock.assert_not_called()


def test_fetch_meta_timeseries_yahoo_stooq_merge():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    yahoo_df = _make_df(["2024-01-01", "2024-01-02"], "Yahoo")
    stooq_df = _make_df(["2024-01-03"], "Stooq")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range", return_value=stooq_df) as stooq_mock, \
        patch.object(meta, "fetch_ft_df") as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    assert df["Source"].tolist() == ["Yahoo", "Yahoo", "Stooq"]
    yahoo_mock.assert_called_once()
    stooq_mock.assert_called_once()
    ft_mock.assert_not_called()


def test_fetch_meta_timeseries_coverage_shortfall():
    start = date(2024, 1, 1)
    end = date(2024, 1, 4)
    yahoo_df = _make_df(["2024-01-01"], "Yahoo")
    stooq_df = _make_df(["2024-01-02"], "Stooq")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range", return_value=stooq_df) as stooq_mock, \
        patch.object(meta, "fetch_ft_df", return_value=pd.DataFrame(columns=STANDARD_COLUMNS)) as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    expected = set(pd.bdate_range(start, end).date)
    assert _coverage_ratio(df, expected) < 0.95
    yahoo_mock.assert_called_once()
    stooq_mock.assert_called_once()
    ft_mock.assert_called_once()


def test_fetch_meta_timeseries_min_coverage_threshold():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    yahoo_df = _make_df(["2024-01-01", "2024-01-02"], "Yahoo")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range") as stooq_mock, \
        patch.object(meta, "fetch_ft_df") as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries(
            "ABC", "L", start_date=start, end_date=end, min_coverage=0.5
        )

    assert df.equals(yahoo_df)
    yahoo_mock.assert_called_once()
    stooq_mock.assert_not_called()
    ft_mock.assert_not_called()


def test_fetch_meta_timeseries_isin_returns_ft_without_other_sources():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    ft_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]).date,
            "Open": [10.0, 10.5, 11.0],
            "High": [10.0, 10.5, 11.0],
            "Low": [10.0, 10.5, 11.0],
            "Close": [10.0, 10.5, 11.0],
            "Volume": [100, 110, 120],
            "Ticker": ["US1234567890"] * 3,
            "Source": ["FT"] * 3,
        }
    )

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "_is_isin", return_value=True) as isin_mock, \
        patch.object(meta, "fetch_ft_df", return_value=ft_df) as ft_mock, \
        patch.object(meta, "fetch_yahoo_timeseries_range") as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range") as stooq_mock, \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=True)):
        df = meta.fetch_meta_timeseries(
            "US1234567890", start_date=start, end_date=end
        )

    assert df.equals(ft_df)
    isin_mock.assert_called_once()
    ft_mock.assert_called_once_with("US1234567890", end, start)
    yahoo_mock.assert_not_called()
    stooq_mock.assert_not_called()


def test_fetch_meta_timeseries_alpha_vantage_rate_limit(monkeypatch):
    start = date(2024, 1, 1)
    end = date(2024, 1, 4)
    fallback_df = _make_df([
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ], "FT")

    import backend.timeseries.fetch_meta_timeseries as meta

    sleep_calls = []

    def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(meta.time, "sleep", fake_sleep)

    with patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(
            meta,
            "fetch_yahoo_timeseries_range",
            return_value=pd.DataFrame(columns=STANDARD_COLUMNS),
        ) as yahoo_mock, \
        patch.object(
            meta,
            "fetch_stooq_timeseries_range",
            return_value=pd.DataFrame(columns=STANDARD_COLUMNS),
        ) as stooq_mock, \
        patch.object(
            meta,
            "fetch_alphavantage_timeseries_range",
            side_effect=meta.AlphaVantageRateLimitError("limit", retry_after=5),
        ) as av_mock, \
        patch.object(meta, "fetch_ft_df", return_value=fallback_df) as ft_mock, \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=True)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    assert df.equals(fallback_df)
    assert sleep_calls == [5]
    yahoo_mock.assert_called_once()
    stooq_mock.assert_called_once()
    av_mock.assert_called_once()
    ft_mock.assert_called_once()

