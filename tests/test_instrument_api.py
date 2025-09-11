import datetime as dt
import logging

import pytest

from backend.common import instrument_api as ia


def _fixed_today(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

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
