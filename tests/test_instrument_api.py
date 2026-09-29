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


def test_close_on_returns_none_for_nan_close(monkeypatch):
    sample_date = dt.date(2023, 1, 8)
    frame = pd.DataFrame({"Date": [sample_date], "Close": [float("nan")]})

    monkeypatch.setattr(ia, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda sym, ex, start_date, end_date: frame)

    assert ia._close_on("AAA", "L", sample_date) is None


def test_close_on_memoizes_only_inside_cache_only(monkeypatch):
    """#8211: _close_on should skip repeat load_meta_timeseries_range calls
    for the same (sym, ex, d) inside cache_only(), but never memoize outside
    it -- a live/background-refresh read must always see fresh data."""
    ia._close_on_cache_only.cache_clear()
    sample_date = dt.date(2023, 1, 8)
    frame = pd.DataFrame({"Date": [sample_date], "Close": [123.45]})
    calls = []

    def fake_load(sym, ex, start_date, end_date):
        calls.append((sym, ex, start_date, end_date))
        return frame

    monkeypatch.setattr(ia, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", fake_load)

    from backend.timeseries.cache import cache_only

    with cache_only():
        assert ia._close_on("AAA", "L", sample_date) == 123.45
        assert ia._close_on("AAA", "L", sample_date) == 123.45
    assert len(calls) == 1, "second cache-only call must hit the memo, not load_meta_timeseries_range again"

    assert ia._close_on("AAA", "L", sample_date) == 123.45
    assert len(calls) == 2, "a call outside cache_only() must never be served from the cache-only memo"


def test_close_on_cache_only_memo_cleared_by_meta_cache_invalidation(monkeypatch):
    """#8211: the new memo must be registered with cache.py's invalidation
    hook so a stale underlying file still busts it, same as the module's own
    meta LRUs."""
    ia._close_on_cache_only.cache_clear()
    sample_date = dt.date(2023, 1, 8)
    calls = []

    def fake_load(sym, ex, start_date, end_date):
        calls.append(1)
        return pd.DataFrame({"Date": [sample_date], "Close": [float(len(calls))]})

    monkeypatch.setattr(ia, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", fake_load)

    from backend.timeseries import cache as cache_mod

    with cache_mod.cache_only():
        first = ia._close_on("AAA", "L", sample_date)
        assert len(calls) == 1

        for clear_fn in cache_mod._EXTRA_META_CACHE_CLEARERS:
            clear_fn()

        second = ia._close_on("AAA", "L", sample_date)
        assert len(calls) == 2, "clearing the registered clearer must force a fresh lookup"
        assert second != first


def test_close_on_cache_only_never_memoizes_a_missing_result(monkeypatch):
    """#8232 review / test_reports_cache_only.py: a missing day (empty frame,
    no cached row) must never be memoized, even inside cache_only(). Missing
    data is exactly the case where load_meta_timeseries_range's caller-side
    refresh_queue.enqueue side effect matters (#7917) -- caching the ``None``
    here would silently suppress that queueing for the rest of this process's
    lifetime, including once real data finally lands, since there is no file
    yet for the invalidation hook to bust this entry with."""
    ia._close_on_cache_only.cache_clear()
    sample_date = dt.date(2023, 1, 8)
    calls = []

    def fake_load(sym, ex, start_date, end_date):
        calls.append(1)
        return pd.DataFrame()

    monkeypatch.setattr(ia, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", fake_load)

    from backend.timeseries.cache import cache_only

    with cache_only():
        assert ia._close_on("AAA", "L", sample_date) is None
        assert ia._close_on("AAA", "L", sample_date) is None
    assert len(calls) == 2, "a missing result must never be served from the memo"


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


def test_top_movers_includes_instrument_type(monkeypatch):
    """#6876: every gainer/loser row carries instrument_type from security meta."""
    _fixed_today(monkeypatch)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: (t, "L"))
    monkeypatch.setattr(ia, "_close_on", lambda sym, ex, d: 100.0)
    monkeypatch.setattr(ia, "price_change_pct", lambda t, d: {"AAA": 5.0, "BBB": -2.0}.get(t))
    monkeypatch.setattr(
        ia,
        "get_security_meta",
        lambda t: {
            "name": f"{t} name",
            "instrument_type": "stock" if t.startswith("AAA") else "etf",
        },
    )

    res = ia.top_movers(["AAA", "BBB"], 7)

    assert [r["instrument_type"] for r in res["gainers"]] == ["stock"]
    assert [r["instrument_type"] for r in res["losers"]] == ["etf"]


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
            "Date": pd.to_datetime(
                [
                    "2024-01-02 10:00:00",
                    "2024-01-02 11:45:00",
                ]
            ),
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


def test_intraday_timeseries_applies_scaling_override(monkeypatch):
    """The live Yahoo fetch (fetch_yahoo_timeseries_period) is never scaled by
    its own data layer -- unlike the two fallback branches in this function,
    which go through timeseries_for_ticker and inherited its scaling fix
    (#6985 review). Without this, a ticker in data/scaling_overrides.json
    would jump ~100x in price depending on whether Yahoo's intraday fetch
    happened to succeed that call, since both branches feed the same
    "prices" contract.
    """
    fixed_now = dt.datetime(2024, 1, 2, 12, 0)

    class FixedDateTime(dt.datetime):
        @classmethod
        def utcnow(cls):
            return fixed_now

    monkeypatch.setattr(ia.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("GSK", "L"))
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {})
    monkeypatch.setattr(ia, "get_scaling_override", lambda *args, **kwargs: 0.01)

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02 11:45:00"]),
            "Close": [1000.0],
        }
    )
    monkeypatch.setattr(
        ia,
        "fetch_yahoo_timeseries_period",
        lambda sym, ex, period, interval, normalize=True: df,
    )

    def _scale_close_only(df_in, scale):
        scaled = df_in.copy()
        scaled["Close"] = scaled["Close"] * scale
        return scaled

    monkeypatch.setattr(ia, "apply_scaling", _scale_close_only)

    res = ia.intraday_timeseries_for_ticker("GSK.L")

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
