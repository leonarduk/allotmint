import pandas as pd
import pytest
import requests
from datetime import date
from types import SimpleNamespace

from backend.timeseries import fetch_stooq_timeseries as fst
from backend.timeseries import fetch_meta_timeseries


def _csv_response():
    return "Date,Open,High,Low,Close,Volume\n2024-01-01,1,1,1,1,0\n"


def test_get_stooq_suffix_aliases():
    assert fst.get_stooq_suffix("LON") == ".UK"
    assert fst.get_stooq_suffix("XLON") == ".UK"
    assert fst.get_stooq_suffix("TSX") == ".TO"


def test_stooq_rate_limit_disables_until_next_day(monkeypatch):
    class Day1(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 1)

    class Day2(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 2)

    class Day3(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 3)

    monkeypatch.setattr(fst, "date", Day1)
    fst.STOOQ_DISABLED_UNTIL = Day1.min
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "record_skipped_ticker", lambda *a, **k: None)

    calls = []

    def rate_limit_get(url, params, **kwargs):
        calls.append("hit")
        return SimpleNamespace(ok=True, status_code=200, text="Exceeded the daily hits limit")

    monkeypatch.setattr(fst.requests, "get", rate_limit_get)

    with pytest.raises(fst.StooqRateLimitError):
        fst.fetch_stooq_timeseries_range("AAA", "L", Day1(2024, 1, 1), Day1(2024, 1, 1))
    assert len(calls) == 1

    def fail_get(url, params, **kwargs):
        raise AssertionError("should not call requests.get while disabled")

    monkeypatch.setattr(fst.requests, "get", fail_get)

    with pytest.raises(fst.StooqRateLimitError):
        fst.fetch_stooq_timeseries_range("AAA", "L", Day1(2024, 1, 1), Day1(2024, 1, 1))

    monkeypatch.setattr(fst, "date", Day2)

    with pytest.raises(fst.StooqRateLimitError):
        fst.fetch_stooq_timeseries_range("AAA", "L", Day1(2024, 1, 1), Day2(2024, 1, 2))

    monkeypatch.setattr(fst, "date", Day3)

    def ok_get(url, params, **kwargs):
        calls.append("ok")
        return SimpleNamespace(ok=True, status_code=200, text=_csv_response())

    monkeypatch.setattr(fst.requests, "get", ok_get)

    df = fst.fetch_stooq_timeseries_range("AAA", "L", Day1(2024, 1, 1), Day3(2024, 1, 3))
    assert not df.empty
    assert len(calls) == 2
    fst.STOOQ_DISABLED_UNTIL = Day1.min


def test_meta_timeseries_handles_stooq_rate_limit(monkeypatch):
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_yahoo_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "fetch_alphavantage_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fetch_meta_timeseries, "_is_isin", lambda *a, **k: False)
    monkeypatch.setattr(fetch_meta_timeseries, "is_valid_ticker", lambda *a, **k: True)

    def raise_limit(*a, **k):
        raise fst.StooqRateLimitError("limit")

    monkeypatch.setattr(fetch_meta_timeseries, "fetch_stooq_timeseries_range", raise_limit)

    def fake_ft(ticker, days):
        return pd.DataFrame({
            "Date": [date(2024, 1, 1)],
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Volume": [0],
            "Ticker": [ticker],
            "Source": ["FT"],
        })

    monkeypatch.setattr(fetch_meta_timeseries, "fetch_ft_timeseries", fake_ft)

    df = fetch_meta_timeseries.fetch_meta_timeseries("AAA", "L", start_date=date(2024,1,1), end_date=date(2024,1,2))
    assert not df.empty
    assert df["Source"].iloc[0] == "FT"


def test_stooq_timeout_returns_empty(monkeypatch, caplog):
    fst.STOOQ_DISABLED_UNTIL = date.min
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "record_skipped_ticker", lambda *a, **k: None)

    def timeout_get(*a, **k):
        raise requests.exceptions.Timeout

    monkeypatch.setattr(fst.requests, "get", timeout_get)
    with caplog.at_level("WARNING"):
        df = fst.fetch_stooq_timeseries_range(
            "AAA", "L", date(2024, 1, 1), date(2024, 1, 2)
        )
    assert df.empty
    assert "timed out" in caplog.text.lower()
