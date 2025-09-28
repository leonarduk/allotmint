import datetime as dt
import logging

import pandas as pd
import pytest

from backend.common import instrument_api as ia


def _fixed_today(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    monkeypatch.setattr(ia.dt, "date", FixedDate)


def _set_today(monkeypatch, target: dt.date) -> None:
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return target

    monkeypatch.setattr(ia.dt, "date", FixedDate)


def test_price_change_pct_unresolved(monkeypatch):
    _fixed_today(monkeypatch)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: None)
    assert ia.price_change_pct("AAA", 7) is None


@pytest.mark.parametrize("px_now, px_then", [(None, 10.0), (10.0, None), (10.0, 0.0)])
def test_price_change_pct_missing_prices(monkeypatch, px_now, px_then):
    _fixed_today(monkeypatch)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("AAA", "L"))

    def fake_close_on(sym: str, ex: str, d: dt.date):
        if d == dt.date(2023, 1, 8):
            return px_now
        if d == dt.date(2023, 1, 1):
            return px_then
        return None

    monkeypatch.setattr(ia, "_close_on", fake_close_on)
    assert ia.price_change_pct("AAA", 7) is None


def test_price_change_pct_warns_small_px_then(monkeypatch, caplog):
    _fixed_today(monkeypatch)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("AAA", "L"))

    def fake_close_on(sym: str, ex: str, d: dt.date):
        if d == dt.date(2023, 1, 8):
            return 1.0
        if d == dt.date(2023, 1, 1):
            return 0.005
        return None

    monkeypatch.setattr(ia, "_close_on", fake_close_on)
    with caplog.at_level(logging.WARNING, logger="instrument_api"):
        assert ia.price_change_pct("AAA", 7) is None
    assert "below threshold" in caplog.text


def test_price_change_pct_warns_large_change(monkeypatch, caplog):
    _fixed_today(monkeypatch)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("AAA", "L"))

    def fake_close_on(sym: str, ex: str, d: dt.date):
        if d == dt.date(2023, 1, 8):
            return 10.0
        if d == dt.date(2023, 1, 1):
            return 1.0
        return None

    monkeypatch.setattr(ia, "_close_on", fake_close_on)
    with caplog.at_level(logging.WARNING, logger="instrument_api"):
        assert ia.price_change_pct("AAA", 7) is None
    assert "exceeds max" in caplog.text


def test_top_movers_filter_and_anomalies(monkeypatch):
    _fixed_today(monkeypatch)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: (t, "L"))
    monkeypatch.setattr(ia, "_close_on", lambda sym, ex, d: 100.0)
    monkeypatch.setattr(
        ia,
        "price_change_pct",
        lambda t, d: {"AAA": 5.0, "BBB": -2.0, "CCC": None}.get(t),
    )
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {"name": f"{t} name"})

    weights = {"AAA": 0.4, "BBB": 0.6, "CCC": 0.7}
    res = ia.top_movers(["AAA", "BBB", "CCC"], 7, min_weight=0.5, weights=weights)

    assert res["gainers"] == []
    assert [r["ticker"] for r in res["losers"]] == ["BBB.L"]
    assert res["anomalies"] == ["CCC"]
    assert all("AAA" not in v for v in (res["gainers"], res["losers"], res["anomalies"]))


def test_intraday_timeseries_success(monkeypatch):
    fixed_now = dt.datetime(2024, 1, 2, 12, 0)

    class FixedDateTime(dt.datetime):
        @classmethod
        def utcnow(cls):
            return fixed_now

    monkeypatch.setattr(ia.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("AAA", "L"))
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {})

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-01-02 10:00:00",
                "2024-01-02 11:45:00",
            ]),
            "Close": [10.0, 11.0],
        }
    )
    monkeypatch.setattr(
        ia,
        "fetch_yahoo_timeseries_period",
        lambda sym, ex, period, interval, normalize=True: df,
    )

    res = ia.intraday_timeseries_for_ticker("AAA.L")
    assert res["last_price_time"] == "2024-01-02T11:45:00"
    assert res["prices"][0]["price"] == pytest.approx(10.0)


def test_intraday_timeseries_fallback(monkeypatch):
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {"instrument_type": "pension"})
    monkeypatch.setattr(
        ia,
        "timeseries_for_ticker",
        lambda t, days=365: {
            "prices": [
                {"date": "2024-01-01", "close": 10.0},
                {"date": "2024-01-02", "close": 11.0},
            ],
            "mini": {},
        },
    )

    res = ia.intraday_timeseries_for_ticker("AAA.L")
    assert res["last_price_time"] == "2024-01-02T00:00:00"
    assert len(res["prices"]) == 2


def test_top_movers_weekend_reporting_date(monkeypatch):
    _set_today(monkeypatch, dt.date(2024, 3, 3))  # Sunday
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("AAA", "L"))
    monkeypatch.setattr(ia, "price_change_pct", lambda t, d: 1.5)
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {"name": "AAA Inc"})

    calls = []

    def fake_close_on(sym: str, ex: str, d: dt.date) -> float:
        calls.append(d)
        return 101.0

    monkeypatch.setattr(ia, "_close_on", fake_close_on)

    res = ia.top_movers(["AAA"], 7)

    assert res["gainers"][0]["last_price_date"] == "2024-03-01"
    assert calls == [dt.date(2024, 3, 1)]


def test_price_and_changes_weekend_reporting_date(monkeypatch):
    _set_today(monkeypatch, dt.date(2024, 3, 3))  # Sunday
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("ABC", "L"))
    monkeypatch.setattr(ia, "price_change_pct", lambda t, d: 2.0)
    from backend.common import portfolio_utils as pu

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})

    calls = []

    def fake_close_on(sym: str, ex: str, d: dt.date) -> float:
        calls.append(d)
        return 55.0

    monkeypatch.setattr(ia, "_close_on", fake_close_on)
    ia._price_and_changes.cache_clear()

    res = ia._price_and_changes("ABC")

    assert res["last_price_date"] == "2024-03-01"
    assert res["last_price_gbp"] == 55.0
    assert calls == [dt.date(2024, 3, 1)]
