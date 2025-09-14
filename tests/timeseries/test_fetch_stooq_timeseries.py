import pandas as pd
import pytest
import requests
from datetime import date
from types import SimpleNamespace

from backend.timeseries import fetch_stooq_timeseries as fst
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


@pytest.fixture(autouse=True)
def reset_stooq_disabled():
    fst.STOOQ_DISABLED_UNTIL = date.min
    yield
    fst.STOOQ_DISABLED_UNTIL = date.min


def _csv_response():
    return "Date,Open,High,Low,Close,Volume\n2024-01-01,1,2,3,4,5\n"


def test_get_stooq_suffix_known_and_unknown():
    assert fst.get_stooq_suffix("LSE") == ".UK"
    assert fst.get_stooq_suffix("NASDAQ") == ".US"
    with pytest.raises(ValueError):
        fst.get_stooq_suffix("UNKNOWN")


def test_format_date():
    assert fst.format_date(date(2024, 5, 6)) == "20240506"


def test_fetch_stooq_timeseries_range_success(monkeypatch):
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "record_skipped_ticker", lambda *a, **k: None)

    def ok_get(url, params, **kwargs):
        assert params["s"] == "AAA.UK"
        return SimpleNamespace(ok=True, status_code=200, text=_csv_response())

    monkeypatch.setattr(fst.requests, "get", ok_get)

    df = fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 1))

    assert not df.empty
    assert list(df.columns) == STANDARD_COLUMNS
    assert df["Ticker"].iloc[0] == "AAA"
    assert df["Source"].iloc[0] == "Stooq"


def test_fetch_stooq_timeseries_range_rate_limit(monkeypatch):
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)

    def limit_get(url, params, **kwargs):
        return SimpleNamespace(ok=True, status_code=200, text="Exceeded the daily hits limit")

    monkeypatch.setattr(fst.requests, "get", limit_get)

    with pytest.raises(fst.StooqRateLimitError):
        fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 2))

    assert fst.STOOQ_DISABLED_UNTIL > date.min


def test_fetch_stooq_timeseries_range_http_error(monkeypatch):
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)

    def http_error_get(url, params, **kwargs):
        return SimpleNamespace(ok=False, status_code=500, text="")

    monkeypatch.setattr(fst.requests, "get", http_error_get)

    with pytest.raises(Exception):
        fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_stooq_timeseries_range_timeout(monkeypatch, caplog):
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)

    def timeout_get(*a, **k):
        raise requests.exceptions.Timeout

    monkeypatch.setattr(fst.requests, "get", timeout_get)

    with caplog.at_level("WARNING"):
        df = fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 2))

    assert df.empty
    assert list(df.columns) == STANDARD_COLUMNS
    assert "timed out" in caplog.text.lower()


def test_fetch_stooq_timeseries_range_invalid_ticker(monkeypatch):
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: False)
    calls = []

    def record(ticker, exchange, reason):
        calls.append((ticker, exchange, reason))

    monkeypatch.setattr(fst, "record_skipped_ticker", record)

    df = fst.fetch_stooq_timeseries_range("BAD", "L", date(2024, 1, 1), date(2024, 1, 2))

    assert df.empty
    assert list(df.columns) == STANDARD_COLUMNS
    assert calls == [("BAD", "L", "unknown")]


def test_fetch_stooq_timeseries_wrapper(monkeypatch):
    class Day(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 10)

    monkeypatch.setattr(fst, "date", Day)

    captured = {}

    def fake_range(ticker, exchange, start_date, end_date):
        captured["args"] = (ticker, exchange, start_date, end_date)
        return pd.DataFrame()

    monkeypatch.setattr(fst, "fetch_stooq_timeseries_range", fake_range)

    fst.fetch_stooq_timeseries("AAA", "L", days=5)

    ticker, exchange, start, end = captured["args"]
    assert ticker == "AAA"
    assert exchange == "L"
    assert start == Day(2024, 1, 5)
    assert end == Day(2024, 1, 10)
