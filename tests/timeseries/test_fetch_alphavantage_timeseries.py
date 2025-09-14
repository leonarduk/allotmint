import pytest
from datetime import date

import backend.timeseries.fetch_alphavantage_timeseries as av
from backend.timeseries.fetch_alphavantage_timeseries import (
    _build_symbol,
    _parse_retry_after,
    fetch_alphavantage_timeseries_range,
    AlphaVantageRateLimitError,
)


@pytest.mark.parametrize(
    "ticker, exchange, expected",
    [
        ("IBM", "US", "IBM"),
        ("vod", "L", "VOD.LON"),
        ("GSK.LON", "L", "GSK.LON"),
        ("BHP", "ASX", "BHP.AX"),
        ("BAS", "DE", "BAS.DE"),
        ("ABC", "UNKNOWN", "ABC"),
    ],
)
def test_build_symbol_various_exchanges(ticker, exchange, expected):
    assert _build_symbol(ticker, exchange) == expected


class FakeResp:
    def __init__(self, status_code=200, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_parse_retry_after_from_header():
    resp = FakeResp(headers={"Retry-After": "7"})
    assert _parse_retry_after(resp, "ignored") == 7


def test_parse_retry_after_header_invalid_uses_message():
    resp = FakeResp(headers={"Retry-After": "foo"})
    assert _parse_retry_after(resp, "wait 5 seconds") == 5


def test_parse_retry_after_minutes_in_message():
    resp = FakeResp()
    assert _parse_retry_after(resp, "retry in 2 minutes") == 120


def test_parse_retry_after_no_hint():
    resp = FakeResp()
    assert _parse_retry_after(resp, "no info") is None


def _patch_validation(monkeypatch):
    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(av, "record_skipped_ticker", lambda *a, **k: None)


def test_fetch_range_http_rate_limit(monkeypatch):
    _patch_validation(monkeypatch)

    def fake_get(*a, **k):
        return FakeResp(status_code=429, headers={"Retry-After": "11"})

    monkeypatch.setattr(av.requests, "get", fake_get)
    with pytest.raises(AlphaVantageRateLimitError) as exc:
        fetch_alphavantage_timeseries_range(
            "AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
        )
    assert exc.value.retry_after == 11


def test_fetch_range_missing_timeseries(monkeypatch):
    _patch_validation(monkeypatch)

    def fake_get(*a, **k):
        return FakeResp(payload={})

    monkeypatch.setattr(av.requests, "get", fake_get)
    with pytest.raises(ValueError) as exc:
        fetch_alphavantage_timeseries_range(
            "AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
        )
    assert "Unexpected response" in str(exc.value)


def test_fetch_range_note_rate_limit(monkeypatch):
    _patch_validation(monkeypatch)

    def fake_get(*a, **k):
        return FakeResp(payload={"Note": "Please try again in 1 minute"})

    monkeypatch.setattr(av.requests, "get", fake_get)
    with pytest.raises(AlphaVantageRateLimitError) as exc:
        fetch_alphavantage_timeseries_range(
            "AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
        )
    assert exc.value.retry_after == 60


def test_fetch_range_success(monkeypatch):
    _patch_validation(monkeypatch)

    payload = {
        "Time Series (Daily)": {
            "2024-01-02": {
                "1. open": "1",
                "2. high": "1.2",
                "3. low": "0.8",
                "4. close": "1.1",
                "6. volume": "1000",
            },
            "2024-01-01": {
                "1. open": "2",
                "2. high": "2.2",
                "3. low": "1.8",
                "4. close": "2.1",
                "6. volume": "2000",
            },
        }
    }

    monkeypatch.setattr(av.requests, "get", lambda *a, **k: FakeResp(payload=payload))

    df = fetch_alphavantage_timeseries_range(
        "AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
    )
    assert not df.empty
    assert list(df.columns) == [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Ticker",
        "Source",
    ]
    assert df["Ticker"].iloc[0] == "AAA"


def test_fetch_range_invalid_ticker(monkeypatch):
    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: False)
    monkeypatch.setattr(av, "record_skipped_ticker", lambda *a, **k: None)

    df = fetch_alphavantage_timeseries_range(
        "BAD", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo"
    )
    assert df.empty


def test_fetch_range_disabled(monkeypatch):
    _patch_validation(monkeypatch)
    monkeypatch.setattr(av.config, "alpha_vantage_enabled", False)

    df = fetch_alphavantage_timeseries_range(
        "AAA", "US", date(2024, 1, 1), date(2024, 1, 2)
    )
    assert df.empty
