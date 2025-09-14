import pytest
from datetime import UTC, datetime, timedelta

from backend import config
from backend.screener import (
    _parse_float,
    _parse_int,
    fetch_fundamentals,
    screen,
    Fundamentals,
)


def test_parse_float():
    assert _parse_float("1.23") == 1.23
    assert _parse_float("None") is None
    assert _parse_float(None) is None
    assert _parse_float("") is None
    assert _parse_float("abc") is None


def test_parse_int():
    assert _parse_int("123") == 123
    assert _parse_int("None") is None
    assert _parse_int(None) is None
    assert _parse_int("") is None
    assert _parse_int("1.2") is None
    assert _parse_int("abc") is None


def test_fetch_fundamentals_caching_and_ttl(monkeypatch):
    sample = {"Name": "Foo", "PERatio": "10.2"}
    call_count = {"n": 0}

    class MockResp:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    def mock_get(url, params, timeout):
        call_count["n"] += 1
        return MockResp()

    monkeypatch.setattr(config.settings, "alpha_vantage_key", "demo")
    monkeypatch.setattr("backend.screener.requests.get", mock_get)
    monkeypatch.setattr("backend.screener._CACHE", {})
    monkeypatch.setattr("backend.screener._CACHE_TTL_SECONDS", 60)

    current_time = [datetime(2024, 1, 1, tzinfo=UTC)]

    class FakeDateTime:
        @classmethod
        def now(cls, tz):
            return current_time[0]

    monkeypatch.setattr("backend.screener.datetime", FakeDateTime)

    f1 = fetch_fundamentals("aapl")
    assert call_count["n"] == 1
    assert f1.pe_ratio == 10.2

    current_time[0] += timedelta(seconds=30)
    f2 = fetch_fundamentals("aapl")
    assert call_count["n"] == 1
    assert f1 is f2

    current_time[0] += timedelta(seconds=31)
    f3 = fetch_fundamentals("aapl")
    assert call_count["n"] == 2
    assert f3.pe_ratio == 10.2


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, ["AAA", "BBB"]),
        ({"peg_max": 1.0, "eps_min": 2}, ["AAA"]),
        ({"peg_max": 0.4, "eps_min": 2}, []),
    ],
)
def test_screen_filters_multiple_tickers(monkeypatch, kwargs, expected):
    def mock_fetch(ticker):
        if ticker == "AAA":
            return Fundamentals(ticker="AAA", peg_ratio=0.5, eps=5)
        return Fundamentals(ticker="BBB", peg_ratio=2.0, eps=1)

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    result = screen(["AAA", "BBB"], **kwargs)
    assert [r.ticker for r in result] == expected
