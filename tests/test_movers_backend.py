import datetime as dt

import pytest

from backend.common import instrument_api as ia


def test_price_change_pct(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(
        ia,
        "_resolve_full_ticker",
        lambda t, latest: (t.split(".", 1)[0], t.split(".", 1)[1] if "." in t else "L"),
    )
    monkeypatch.setattr(ia, "_LATEST_PRICES", {})

    def fake_close_on(sym: str, ex: str, d: dt.date):
        if d == dt.date(2023, 1, 8):
            return 110.0
        if d == dt.date(2023, 1, 1):
            return 100.0
        return None

    monkeypatch.setattr(ia, "_close_on", fake_close_on)

    assert ia.price_change_pct("AAA.L", 7) == pytest.approx(10.0)
    assert ia.price_change_pct("AAA.L", 30) is None


def test_top_movers(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(
        ia,
        "_resolve_full_ticker",
        lambda t, latest: (t.split(".", 1)[0], t.split(".", 1)[1] if "." in t else "L"),
    )
    monkeypatch.setattr(ia, "_LATEST_PRICES", {})
    monkeypatch.setattr(ia, "_close_on", lambda sym, ex, d: 100.0)
    monkeypatch.setattr(
        ia,
        "price_change_pct",
        lambda t, d: {"AAA.L": 5.0, "BBB.L": -2.0, "CCC.L": 1.0}.get(t),
    )
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {"name": f"{t} name"})

    res = ia.top_movers(["AAA.L", "BBB.L", "CCC.L"], 7, limit=2)
    assert [r["ticker"] for r in res["gainers"]] == ["AAA.L", "CCC.L"]
    assert [r["ticker"] for r in res["losers"]] == ["BBB.L"]
    assert res["gainers"][0]["last_price_gbp"] == 100.0
    assert res["gainers"][0]["last_price_date"] == "2023-01-08"


def test_top_movers_min_weight(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(
        ia,
        "_resolve_full_ticker",
        lambda t, latest: (t.split(".", 1)[0], t.split(".", 1)[1] if "." in t else "L"),
    )
    monkeypatch.setattr(ia, "_LATEST_PRICES", {})
    monkeypatch.setattr(ia, "_close_on", lambda sym, ex, d: 100.0)
    monkeypatch.setattr(
        ia,
        "price_change_pct",
        lambda t, d: {"AAA.L": 5.0, "BBB.L": -2.0, "CCC.L": 1.0}.get(t),
    )
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {"name": f"{t} name"})

    weights = {"AAA.L": 1.0, "BBB.L": 0.4, "CCC.L": 0.6}
    res = ia.top_movers(
        ["AAA.L", "BBB.L", "CCC.L"],
        7,
        limit=2,
        min_weight=0.5,
        weights=weights,
    )
    assert [r["ticker"] for r in res["gainers"]] == ["AAA.L", "CCC.L"]
    assert [r["ticker"] for r in res["losers"]] == []


def test_top_movers_anomaly(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(
        ia,
        "_resolve_full_ticker",
        lambda t, latest: (t.split(".", 1)[0], t.split(".", 1)[1] if "." in t else "L"),
    )
    monkeypatch.setattr(ia, "_LATEST_PRICES", {})

    def fake_close_on(sym: str, ex: str, d: dt.date):
        if d == dt.date(2023, 1, 8):
            return 100.0
        if d == dt.date(2023, 1, 1):
            return 0.0001
        return None

    monkeypatch.setattr(ia, "_close_on", fake_close_on)

    res = ia.top_movers(["AAA.L"], 7, limit=5)
    assert res["gainers"] == []
    assert res["losers"] == []
    assert "AAA.L" in res["anomalies"]
