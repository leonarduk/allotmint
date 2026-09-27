from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

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


@pytest.mark.parametrize("exc", [requests.exceptions.Timeout, requests.exceptions.ConnectionError])
def test_unreachable_stooq_is_skipped_during_cooldown(monkeypatch, exc):
    """After a timeout/connection failure Stooq is not called again until the cooldown ends (#7877)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    now = [1000.0]
    monkeypatch.setattr(fst, "monotonic", lambda: now[0])
    calls = []

    def failing_get(*a, **k):
        calls.append(1)
        raise exc

    monkeypatch.setattr(fst.requests, "get", failing_get)

    first = fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 2))
    assert first.empty
    assert len(calls) == 1

    with pytest.raises(fst.StooqRateLimitError):
        fst.fetch_stooq_timeseries_range("BBB", "L", date(2024, 1, 1), date(2024, 1, 2))
    assert len(calls) == 1

    now[0] += fst.STOOQ_UNREACHABLE_COOLDOWN_SECONDS
    monkeypatch.setattr(
        fst.requests, "get", lambda *a, **k: SimpleNamespace(ok=True, status_code=200, text=_csv_response())
    )
    recovered = fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 1))
    assert not recovered.empty


def test_daily_limit_takes_precedence_over_unreachable_cooldown(monkeypatch):
    """The daily-limit guard still raises its own error while the unreachable cooldown is active (#7877)."""
    monkeypatch.setattr(fst, "monotonic", lambda: 1000.0)
    fst._mark_stooq_unreachable()
    monkeypatch.setattr(fst, "STOOQ_DISABLED_UNTIL", date.today())
    monkeypatch.setattr(fst.requests, "get", lambda *a, **k: pytest.fail("Stooq should not be called"))

    with pytest.raises(fst.StooqRateLimitError, match="daily hits limit"):
        fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 2))


def test_invalid_ticker_is_recorded_as_skipped_during_cooldown(monkeypatch):
    """An unrecognized ticker is still skipped and recorded, not reported as a cooldown (#7877)."""
    monkeypatch.setattr(fst, "monotonic", lambda: 1000.0)
    fst._mark_stooq_unreachable()
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: False)
    skipped = []
    monkeypatch.setattr(fst, "record_skipped_ticker", lambda *a, **k: skipped.append(a))

    result = fst.fetch_stooq_timeseries_range("BAD", "L", date(2024, 1, 1), date(2024, 1, 2))

    assert result.empty
    assert skipped == [("BAD", "L")]


def _ok_response(*a, **k):
    return SimpleNamespace(ok=True, status_code=200, text=_csv_response())


@pytest.mark.parametrize("exc", [requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError])
def test_connection_failure_starts_global_cooldown(monkeypatch, exc):
    """A connect-level failure still skips Stooq for every ticker (#7877, #7913)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "monotonic", lambda: 1000.0)
    calls = []

    def failing_get(*a, **k):
        calls.append(1)
        raise exc

    monkeypatch.setattr(fst.requests, "get", failing_get)

    assert fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 2)).empty
    with pytest.raises(fst.StooqRateLimitError, match="unreachable"):
        fst.fetch_stooq_timeseries_range("BBB", "L", date(2024, 1, 1), date(2024, 1, 2))
    assert len(calls) == 1


def test_read_timeout_skips_only_that_ticker(monkeypatch, caplog):
    """A read timeout on one ticker does not block Stooq for other tickers (#7913)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    now = [1000.0]
    monkeypatch.setattr(fst, "monotonic", lambda: now[0])
    calls = []

    def get(url, params, **kwargs):
        calls.append(params["s"])
        if params["s"] == "SLOW.UK":
            raise requests.exceptions.ReadTimeout
        return _ok_response()

    monkeypatch.setattr(fst.requests, "get", get)

    with caplog.at_level("WARNING"):
        slow = fst.fetch_stooq_timeseries_range("SLOW", "L", date(2024, 1, 1), date(2024, 1, 1))
    assert slow.empty
    assert "skipping this ticker" in caplog.text

    other = fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 1))
    assert not other.empty

    with pytest.raises(fst.StooqRateLimitError, match="this ticker"):
        fst.fetch_stooq_timeseries_range("SLOW", "L", date(2024, 1, 1), date(2024, 1, 1))
    assert calls == ["SLOW.UK", "AAA.UK"]

    now[0] += fst.STOOQ_TICKER_SKIP_SECONDS
    assert fst.fetch_stooq_timeseries_range("SLOW", "L", date(2024, 1, 1), date(2024, 1, 1)).empty
    assert calls == ["SLOW.UK", "AAA.UK", "SLOW.UK"]


def test_consecutive_read_timeouts_start_global_cooldown(monkeypatch):
    """A host that accepts connections but never answers is capped at a few timeouts (#7913)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "monotonic", lambda: 1000.0)
    calls = []

    def hanging_get(url, params, **kwargs):
        calls.append(params["s"])
        raise requests.exceptions.ReadTimeout

    monkeypatch.setattr(fst.requests, "get", hanging_get)

    limit = fst.STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN
    for i in range(limit):
        assert fst.fetch_stooq_timeseries_range(f"T{i}", "L", date(2024, 1, 1), date(2024, 1, 2)).empty

    with pytest.raises(fst.StooqRateLimitError, match="unreachable"):
        fst.fetch_stooq_timeseries_range("OTHER", "L", date(2024, 1, 1), date(2024, 1, 2))
    assert len(calls) == limit


def test_response_resets_consecutive_read_timeouts(monkeypatch):
    """Scattered read timeouts separated by successful responses never trip the global cooldown (#7913)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "monotonic", lambda: 1000.0)

    def get(url, params, **kwargs):
        if params["s"].startswith("SLOW"):
            raise requests.exceptions.ReadTimeout
        return _ok_response()

    monkeypatch.setattr(fst.requests, "get", get)

    for i in range(fst.STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN * 2):
        assert fst.fetch_stooq_timeseries_range(f"SLOW{i}", "L", date(2024, 1, 1), date(2024, 1, 1)).empty
        assert not fst.fetch_stooq_timeseries_range("AAA", "L", date(2024, 1, 1), date(2024, 1, 1)).empty


def test_error_response_does_not_reset_consecutive_read_timeouts(monkeypatch):
    """An HTTP error page between read timeouts still lets the global cooldown start (#7913)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(fst, "monotonic", lambda: 1000.0)

    def get(url, params, **kwargs):
        if params["s"].startswith("SLOW"):
            raise requests.exceptions.ReadTimeout
        return SimpleNamespace(ok=False, status_code=503, text="")

    monkeypatch.setattr(fst.requests, "get", get)

    for i in range(fst.STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN):
        assert fst.fetch_stooq_timeseries_range(f"SLOW{i}", "L", date(2024, 1, 1), date(2024, 1, 1)).empty
        if i < fst.STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN - 1:
            with pytest.raises(Exception, match="HTTP error 503"):
                fst.fetch_stooq_timeseries_range(f"ERR{i}", "L", date(2024, 1, 1), date(2024, 1, 1))

    with pytest.raises(fst.StooqRateLimitError, match="unreachable"):
        fst.fetch_stooq_timeseries_range("OTHER", "L", date(2024, 1, 1), date(2024, 1, 1))


def test_connection_cooldown_resets_consecutive_read_timeouts(monkeypatch):
    """Read timeouts before a connection-error cooldown don't count toward the next one (#7913)."""
    monkeypatch.setattr(fst, "is_valid_ticker", lambda *a, **k: True)
    now = [1000.0]
    monkeypatch.setattr(fst, "monotonic", lambda: now[0])
    failure = [requests.exceptions.ReadTimeout]

    def get(url, params, **kwargs):
        raise failure[0]

    monkeypatch.setattr(fst.requests, "get", get)

    for i in range(fst.STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN - 1):
        fst.fetch_stooq_timeseries_range(f"SLOW{i}", "L", date(2024, 1, 1), date(2024, 1, 1))
    failure[0] = requests.exceptions.ConnectionError
    fst.fetch_stooq_timeseries_range("DOWN", "L", date(2024, 1, 1), date(2024, 1, 1))

    now[0] += fst.STOOQ_UNREACHABLE_COOLDOWN_SECONDS
    failure[0] = requests.exceptions.ReadTimeout
    fst.fetch_stooq_timeseries_range("AFTER", "L", date(2024, 1, 1), date(2024, 1, 1))

    monkeypatch.setattr(fst.requests, "get", _ok_response)
    assert not fst.fetch_stooq_timeseries_range("OTHER", "L", date(2024, 1, 1), date(2024, 1, 1)).empty
