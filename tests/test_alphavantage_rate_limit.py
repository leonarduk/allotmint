import pandas as pd
import pytest
from datetime import date

import backend.timeseries.fetch_alphavantage_timeseries as av
from backend.timeseries.fetch_alphavantage_timeseries import (
    fetch_alphavantage_timeseries_range,
    AlphaVantageRateLimitError,
)
import backend.timeseries.fetch_meta_timeseries as fm


class _Resp429:
    status_code = 429
    headers = {"Retry-After": "12"}

    def json(self):
        return {}

    def raise_for_status(self):
        pass


class _RespNote:
    status_code = 200
    headers = {}

    def json(self):
        return {"Note": "Please try again in 60 seconds."}

    def raise_for_status(self):
        pass


def test_http_429_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(av, "record_skipped_ticker", lambda *a, **k: None)
    monkeypatch.setattr(av.requests, "get", lambda *a, **k: _Resp429())

    with pytest.raises(AlphaVantageRateLimitError) as exc:
        fetch_alphavantage_timeseries_range(
            "AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
        )
    assert exc.value.retry_after == 12


def test_note_field_triggers_rate_limit(monkeypatch):
    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(av, "record_skipped_ticker", lambda *a, **k: None)
    monkeypatch.setattr(av.requests, "get", lambda *a, **k: _RespNote())

    with pytest.raises(AlphaVantageRateLimitError) as exc:
        fetch_alphavantage_timeseries_range(
            "AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
        )
    assert exc.value.retry_after == 60


def test_meta_timeseries_handles_av_rate_limit(monkeypatch):
    monkeypatch.setattr(fm, "fetch_yahoo_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fm, "fetch_stooq_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(fm, "_is_isin", lambda *a, **k: False)
    monkeypatch.setattr(fm, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fm.config, "alpha_vantage_enabled", True)
    monkeypatch.setattr(fm.time, "sleep", lambda *a, **k: None)

    def raise_limit(*a, **k):
        raise AlphaVantageRateLimitError("limit", retry_after=0)

    monkeypatch.setattr(fm, "fetch_alphavantage_timeseries_range", raise_limit)

    def fake_ft(ticker, days):
        return pd.DataFrame(
            {
                "Date": [date(2024, 1, 1)],
                "Open": [1.0],
                "High": [1.0],
                "Low": [1.0],
                "Close": [1.0],
                "Volume": [0],
                "Ticker": [ticker],
                "Source": ["FT"],
            }
        )

    monkeypatch.setattr(fm, "fetch_ft_timeseries", fake_ft)

    df = fm.fetch_meta_timeseries(
        "AAA", "L", start_date=date(2024, 1, 1), end_date=date(2024, 1, 2)
    )
    assert not df.empty
    assert df["Source"].iloc[0] == "FT"
