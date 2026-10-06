from datetime import date

import pytest

import backend.timeseries.fetch_alphavantage_timeseries as av
from backend.common.url_validator import InvalidExternalURLError
from backend.timeseries.fetch_alphavantage_timeseries import (
    AlphaVantageRateLimitError,
    _build_symbol,
    _parse_retry_after,
    fetch_alphavantage_timeseries_range,
)
from backend.timeseries.source_basis import DIVIDEND_ADJUSTED_SOURCES


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
        fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")
    assert exc.value.retry_after == 11


def test_fetch_range_missing_timeseries(monkeypatch):
    _patch_validation(monkeypatch)

    def fake_get(*a, **k):
        return FakeResp(payload={})

    monkeypatch.setattr(av.requests, "get", fake_get)
    with pytest.raises(ValueError) as exc:
        fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")
    assert "Unexpected response" in str(exc.value)


def test_fetch_range_note_rate_limit(monkeypatch):
    _patch_validation(monkeypatch)

    def fake_get(*a, **k):
        return FakeResp(payload={"Note": "Please try again in 1 minute"})

    monkeypatch.setattr(av.requests, "get", fake_get)
    with pytest.raises(AlphaVantageRateLimitError) as exc:
        fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")
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

    df = fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")
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


def test_fetch_range_keeps_sub_one_and_pence_precision(monkeypatch):
    """Prices are stored to six significant figures, not 2 dp (#9369)."""
    _patch_validation(monkeypatch)
    payload = {
        "Time Series (Daily)": {
            "2024-01-02": {
                "1. open": "0.9399",
                "2. high": "0.9449",
                "3. low": "0.9387",
                "4. close": "0.9416",
                "6. volume": "1000",
            },
            "2024-01-01": {
                "1. open": "4567.25",
                "2. high": "4580.5",
                "3. low": "4551.0",
                "4. close": "4573.5",
                "6. volume": "2000",
            },
        }
    }
    monkeypatch.setattr(av.requests, "get", lambda *a, **k: FakeResp(payload=payload))

    df = fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")

    assert df["Close"].tolist() == [4573.5, 0.9416]
    assert df["Open"].tolist() == [4567.25, 0.9399]
    assert df["Close"].dtype == "float64"


def test_fetch_range_invalid_ticker(monkeypatch):
    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: False)
    monkeypatch.setattr(av, "record_skipped_ticker", lambda *a, **k: None)

    df = fetch_alphavantage_timeseries_range("BAD", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")
    assert df.empty


def test_fetch_range_disabled(monkeypatch):
    _patch_validation(monkeypatch)
    monkeypatch.setattr(av.config, "alpha_vantage_enabled", False)

    df = fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2))
    assert df.empty


@pytest.mark.parametrize(
    "bad_url",
    [
        pytest.param("https://169.254.169.254/query", id="aws_metadata"),
        pytest.param("https://127.0.0.1/query", id="loopback"),
        pytest.param("https://10.0.0.1/query", id="rfc1918"),
        pytest.param("https://localhost/query", id="localhost"),
    ],
)
def test_fetch_range_rejects_private_base_url(monkeypatch, bad_url: str) -> None:
    # _patch_validation stubs out is_valid_ticker (-> True) and
    # record_skipped_ticker (-> no-op) so neither early-return guard fires.
    # Passing api_key="demo" bypasses the alpha_vantage_enabled check.
    # The function therefore reaches validate_external_url(BASE_URL) where
    # BASE_URL has been monkeypatched to bad_url, triggering the SSRF guard.
    _patch_validation(monkeypatch)
    monkeypatch.setattr(av, "BASE_URL", bad_url)
    with pytest.raises(InvalidExternalURLError):
        fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 2), api_key="demo")


def _day(close, *, adjusted=None, split="1.0", volume="1000"):
    return {
        "1. open": close,
        "2. high": close,
        "3. low": close,
        "4. close": close,
        "5. adjusted close": adjusted or close,
        "6. volume": volume,
        "7. dividend amount": "0.0000",
        "8. split coefficient": split,
    }


def test_fetch_range_stores_traded_close_not_adjusted_close(monkeypatch):
    """``4. close`` is stored; the dividend-adjusted ``5. adjusted close`` never is (#9340)."""
    _patch_validation(monkeypatch)
    payload = {
        "Time Series (Daily)": {
            "2024-01-03": _day("100.0"),
            "2024-01-02": _day("101.0", adjusted="98.5"),
            "2024-01-01": _day("102.0", adjusted="99.4"),
        }
    }
    rows = payload["Time Series (Daily)"].values()
    assert any(r["4. close"] != r["5. adjusted close"] for r in rows)  # not vacuous
    monkeypatch.setattr(av.requests, "get", lambda *a, **k: FakeResp(payload=payload))

    df = fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 3), api_key="demo")

    assert df["Close"].tolist() == [102.0, 101.0, 100.0]
    assert df["Source"].iloc[0] not in DIVIDEND_ADJUSTED_SOURCES
    assert df["Volume"].tolist() == [1000, 1000, 1000]


def test_fetch_range_split_adjusts_rows_before_a_split(monkeypatch):
    """A 4:1 split on 2024-01-03: earlier rows are divided by 4 and volume multiplied by 4."""
    _patch_validation(monkeypatch)
    payload = {
        "Time Series (Daily)": {
            "2024-01-04": _day("26.0"),
            "2024-01-03": _day("25.0", split="4.0"),
            "2024-01-02": _day("102.0", volume="500"),
            "2024-01-01": _day("100.0", volume="250"),
        }
    }
    monkeypatch.setattr(av.requests, "get", lambda *a, **k: FakeResp(payload=payload))

    df = fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 4), api_key="demo")

    assert df["Close"].tolist() == [25.0, 25.5, 25.0, 26.0]
    assert df["Open"].tolist() == [25.0, 25.5, 25.0, 26.0]
    assert df["Volume"].tolist() == [1000.0, 2000.0, 1000.0, 1000.0]


def test_fetch_range_applies_splits_after_the_requested_range(monkeypatch):
    """A split after ``end_date`` still rescales the rows inside the range, as Yahoo's history does."""
    _patch_validation(monkeypatch)
    payload = {
        "Time Series (Daily)": {
            "2024-03-01": _day("10.0", split="2.0"),
            "2024-02-01": _day("30.0", split="1.5"),
            "2024-01-02": _day("60.0"),
        }
    }
    monkeypatch.setattr(av.requests, "get", lambda *a, **k: FakeResp(payload=payload))

    df = fetch_alphavantage_timeseries_range("AAA", "US", date(2024, 1, 1), date(2024, 1, 31), api_key="demo")

    assert df["Close"].tolist() == [20.0]


@pytest.mark.parametrize("coefficient", ["0.0", "", "n/a", "-2"])
def test_split_adjust_ignores_unusable_coefficients(coefficient):
    import pandas as pd

    df = pd.DataFrame(
        {"Close": ["10.0", "11.0"], "Volume": ["5", "6"], av.SPLIT_COEFFICIENT_FIELD: ["1.0", coefficient]}
    )
    out = av.split_adjust(df)
    assert out["Close"].tolist() == ["10.0", "11.0"]


def test_split_adjust_without_coefficients_is_a_no_op():
    import pandas as pd

    df = pd.DataFrame({"Close": [10.0, 11.0]})
    assert av.split_adjust(df)["Close"].tolist() == [10.0, 11.0]
