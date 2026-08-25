import datetime as dt

import pandas as pd

from backend.common import instrument_api as ia


def test_resolve_full_ticker_variants(monkeypatch):
    """Tickers with/without exchanges and unknown symbols."""

    monkeypatch.setattr(ia, "_TICKER_EXCHANGE_MAP", {"BAR": "L"})

    # Explicit exchange is returned unchanged
    assert ia._resolve_full_ticker("FOO.L", {}) == ("FOO", "L")

    # Exchange inferred from latest prices
    latest = {"FOO.L": 1.0}
    assert ia._resolve_full_ticker("FOO", latest) == ("FOO", "L")

    # Exchange inferred from cached mapping
    assert ia._resolve_full_ticker("BAR", {}) == ("BAR", "L")

    # Unknown symbol returns None
    assert ia._resolve_full_ticker("BAZ", {}) is None


def test_prime_latest_prices_respects_skip(monkeypatch):
    monkeypatch.setattr(ia.config, "skip_snapshot_warm", True)

    called = {"value": False}

    def fake_load(_):
        called["value"] = True
        return {"AAA": 1.0}

    monkeypatch.setattr(ia, "load_latest_prices", fake_load)
    ia._LATEST_PRICES = {"OLD": 2.0}
    ia.prime_latest_prices()
    assert ia._LATEST_PRICES == {}
    assert called["value"] is False


def test_prime_latest_prices_populates(monkeypatch):
    monkeypatch.setattr(ia.config, "skip_snapshot_warm", False)
    monkeypatch.setattr(ia, "_ALL_TICKERS", ["AAA", "BBB"])

    captured = {}

    def fake_load(tickers):
        captured["tickers"] = tickers
        return {"AAA": 1.23}

    monkeypatch.setattr(ia, "load_latest_prices", fake_load)
    ia._LATEST_PRICES = {}
    ia.prime_latest_prices()
    assert ia._LATEST_PRICES == {"AAA": 1.23}
    assert captured["tickers"] == ["AAA", "BBB"]


def test_timeseries_for_ticker_missing_data(monkeypatch):
    def fake_resolve(ticker, latest):
        return ("XYZ", "L")

    monkeypatch.setattr(ia, "_resolve_full_ticker", fake_resolve)
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: None)

    res = ia.timeseries_for_ticker("XYZ", days=1)
    assert res == {"prices": [], "mini": {"7": [], "30": [], "180": []}}


def test_timeseries_for_ticker_renames_columns(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    df = pd.DataFrame({"Date": pd.to_datetime(["2023-01-08"]), "Close_gbp": [2.0]})

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("XYZ", "L"))
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: df)

    res = ia.timeseries_for_ticker("XYZ", days=1)
    assert res["prices"] == [{"date": "2023-01-08", "close": 2.0, "close_gbp": 2.0}]
    assert res["mini"] == {"7": res["prices"], "30": res["prices"], "180": res["prices"]}


def test_timeseries_for_ticker_applies_scaling_override(monkeypatch):
    """LSE sources often report price in pence; get_scaling_override/apply_scaling
    correct for this on the single-instrument /instrument route (routes/instrument.py's
    own hand-rolled dataframe pipeline) but this shared helper had no equivalent, so a
    ticker in data/scaling_overrides.json (e.g. GSK.L, LLOY.L) would read up to 100x too
    high wherever this function is used instead -- /instrument/batch and portfolio.py's
    instrument_detail (#6985 review)."""

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    df = pd.DataFrame({"date": ["2023-01-08"], "close": [100.0], "close_gbp": [100.0]})

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("XYZ", "L"))
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: df)
    monkeypatch.setattr(ia, "get_scaling_override", lambda *args, **kwargs: 0.01)

    def _scale_close(df_in, scale):
        scaled = df_in.copy()
        scaled["close"] = scaled["close"] * scale
        return scaled

    monkeypatch.setattr(ia, "apply_scaling", _scale_close)

    res = ia.timeseries_for_ticker("XYZ", days=1)

    assert res["prices"] == [{"date": "2023-01-08", "close": 1.0, "close_gbp": 1.0}]


def test_timeseries_for_ticker_scaling_noop_skips_apply_scaling(monkeypatch):
    """scale == 1.0 (no override configured -- the overwhelming common case) must
    short-circuit rather than call apply_scaling, matching its own no-op contract."""

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    df = pd.DataFrame({"date": ["2023-01-08"], "close": [100.0], "close_gbp": [100.0]})

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("XYZ", "L"))
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: df)
    monkeypatch.setattr(ia, "get_scaling_override", lambda *args, **kwargs: 1.0)

    def _fail_if_called(df_in, scale):
        raise AssertionError("apply_scaling must not be called when scale == 1.0")

    monkeypatch.setattr(ia, "apply_scaling", _fail_if_called)

    res = ia.timeseries_for_ticker("XYZ", days=1)

    assert res["prices"] == [{"date": "2023-01-08", "close": 100.0, "close_gbp": 100.0}]


def test_timeseries_for_ticker_mini_slices(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 7, 20)

    dates = pd.date_range("2023-01-01", periods=200, freq="D")
    df = pd.DataFrame({"date": dates, "close": range(200)})

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("XYZ", "L"))
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: df)

    res = ia.timeseries_for_ticker("XYZ", days=200)
    assert len(res["prices"]) == 200
    assert res["mini"]["7"] == res["prices"][-7:]
    assert res["mini"]["30"] == res["prices"][-30:]
    assert res["mini"]["180"] == res["prices"][-180:]


def test_timeseries_for_ticker_inverted_range_returns_empty(monkeypatch):
    """Inverted start/end (start > end) returns the empty payload without hitting the cache."""
    calls: list[str] = []

    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("XYZ", "L"))
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(
        ia,
        "load_meta_timeseries_range",
        lambda s, e, start_date, end_date: calls.append("called") or pd.DataFrame(),
    )

    res = ia.timeseries_for_ticker(
        "XYZ",
        start_date=dt.date(2024, 6, 1),
        end_date=dt.date(2024, 1, 1),  # end before start
    )

    assert res == {"prices": [], "mini": {"7": [], "30": [], "180": []}}
    assert calls == [], "load_meta_timeseries_range must not be called for an inverted range"
