"""Live quotes must share units with the stored closes they sit beside."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backend.common import holding_utils, live_prices
from backend.timeseries import cache

NOW_TS = int(dt.datetime.now(dt.timezone.utc).timestamp())


def _instrument(monkeypatch, *, currency: str, scale: float, fx_rate: float | None = None) -> None:
    """Pin the metadata currency, scaling override and FX rate on every path that reads them."""
    meta = lambda *_a, **_k: {"currency": currency}  # noqa: E731
    monkeypatch.setattr(cache, "get_instrument_meta", meta)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", meta)
    for module in (holding_utils, live_prices):
        monkeypatch.setattr(module, "get_scaling_override", lambda *_a, **_k: scale)

    def _fx(_curr, start, end, **_k):
        if fx_rate is None:
            return pd.DataFrame(columns=["Date", "Rate"])
        days = pd.date_range(start - dt.timedelta(days=7), end)
        return pd.DataFrame({"Date": days, "Rate": [fx_rate] * len(days)})

    monkeypatch.setattr(cache, "_load_fx_rates", _fx)
    monkeypatch.setattr(holding_utils, "_fx_to_base", lambda *_a, **_k: fx_rate)


def _stored_close(monkeypatch, raw_close: float) -> None:
    """Make the range loader find ``raw_close`` for today, before its own FX step."""
    frame = pd.DataFrame({"Date": [pd.Timestamp(dt.date.today())], "Close": [raw_close]})
    monkeypatch.setattr(cache, "_invalidate_meta_caches_if_stale", lambda *_a: None)
    monkeypatch.setattr(cache, "_memoized_range", lambda *_a: frame.copy())


@pytest.mark.parametrize(
    ("full", "yahoo_symbol", "currency", "scale", "fx_rate", "raw", "expected_gbp"),
    [
        # US listing: FX from the timeseries loader's own conversion.
        ("ADBE.N", "ADBE", "USD", 1.0, 0.75, 400.0, 300.0),
        # GBX metadata, pence factor override: scaled once, never re-divided.
        ("HFEL.L", "HFEL.L", "GBX", 0.01, None, 250.0, 2.5),
        # #6845: metadata says GBP but the feed is pence; only the override fixes it.
        ("GSK.L", "GSK.L", "GBP", 0.01, None, 1888.0, 18.88),
        # GBX with a non-pence override still gets the pence conversion.
        ("ABC.L", "ABC.L", "GBX", 0.5, None, 200.0, 1.0),
    ],
)
def test_live_gbp_price_matches_stored_close_for_same_raw_value(
    monkeypatch, stub_live_quotes, full, yahoo_symbol, currency, scale, fx_rate, raw, expected_gbp
):
    _instrument(monkeypatch, currency=currency, scale=scale, fx_rate=fx_rate)
    _stored_close(monkeypatch, raw)
    stub_live_quotes({yahoo_symbol: (raw, NOW_TS)})

    with cache.cache_only():
        stored_gbp = holding_utils.load_latest_closes([full])[full][0]
    live = live_prices.load_live_quotes([full])[full]

    assert stored_gbp == pytest.approx(expected_gbp)
    assert live["price_gbp"] == pytest.approx(stored_gbp)


def test_native_price_takes_override_like_instrument_close(monkeypatch, stub_live_quotes):
    _instrument(monkeypatch, currency="GBP", scale=0.01)
    stub_live_quotes({"GSK.L": (1888.0, NOW_TS)})
    monkeypatch.setattr(
        live_prices,
        "_fetch_raw",
        lambda _sym: {
            "regularMarketPrice": 1888.0,
            "regularMarketPreviousClose": 1850.0,
            "regularMarketTime": NOW_TS,
            "marketState": "REGULAR",
        },
    )

    quote = live_prices.load_live_quotes(["gsk.l"])["GSK.L"]

    assert quote["price"] == pytest.approx(18.88)
    assert quote["previous_close"] == pytest.approx(18.50)
    assert quote["currency"] == "GBP"
    assert quote["change_pct"] == pytest.approx((1888 - 1850) / 1850 * 100)
    assert quote["market_state"] == "REGULAR"
    assert quote["is_stale"] is False


def test_us_quote_keeps_native_usd_price(monkeypatch, stub_live_quotes):
    _instrument(monkeypatch, currency="USD", scale=1.0, fx_rate=0.8)
    stub_live_quotes({"ADBE": (410.0, NOW_TS)})

    quote = live_prices.load_live_quotes(["ADBE.N"])["ADBE.N"]

    assert quote["price"] == pytest.approx(410.0)
    assert quote["currency"] == "USD"
    assert quote["price_gbp"] == pytest.approx(328.0)


def test_quote_a_power_of_ten_off_the_last_close_is_dropped(monkeypatch, stub_live_quotes):
    """A feed quoting pence for a series stored in pounds must not render 100x out."""
    _instrument(monkeypatch, currency="GBP", scale=1.0)
    stub_live_quotes({"AV.L": (550.0, NOW_TS)}, last_closes={"AV.L": (5.5, dt.date.today())})

    assert live_prices.load_live_quotes(["AV.L"]) == {}


def test_ordinary_move_from_last_close_is_kept(monkeypatch, stub_live_quotes):
    _instrument(monkeypatch, currency="GBP", scale=1.0)
    stub_live_quotes({"AV.L": (5.9, NOW_TS)}, last_closes={"AV.L": (5.5, dt.date.today())})

    assert live_prices.load_live_quotes(["AV.L"])["AV.L"]["price_gbp"] == pytest.approx(5.9)


def test_old_quote_is_flagged_stale(monkeypatch, stub_live_quotes):
    _instrument(monkeypatch, currency="GBP", scale=1.0)
    stub_live_quotes({"AV.L": (5.9, NOW_TS - 3600)})

    assert live_prices.load_live_quotes(["AV.L"])["AV.L"]["is_stale"] is True


def test_no_fx_rate_means_no_live_price(monkeypatch, stub_live_quotes):
    _instrument(monkeypatch, currency="USD", scale=1.0, fx_rate=None)
    stub_live_quotes({"ADBE": (410.0, NOW_TS)})

    assert live_prices.load_live_quotes(["ADBE.N"]) == {}


def test_unsupported_exchange_and_missing_quotes_are_skipped(monkeypatch, stub_live_quotes):
    _instrument(monkeypatch, currency="GBP", scale=1.0)
    stub_live_quotes({})

    assert live_prices.load_live_quotes(["FOO.ZZ", "BAR.L"]) == {}


def test_offline_mode_fetches_nothing(monkeypatch):
    monkeypatch.setattr(live_prices.config, "offline_mode", True)
    monkeypatch.setattr(live_prices, "_fetch_raw", lambda _s: pytest.fail("fetched in offline mode"))

    assert live_prices.load_live_quotes(["ADBE.N"]) == {}


def test_raw_quotes_are_cached_briefly(monkeypatch):
    live_prices.clear_quote_cache()
    calls: list[str] = []

    def _chart(ticker):
        calls.append(ticker)
        return {"regularMarketPrice": 1.0, "regularMarketTime": NOW_TS}

    monkeypatch.setattr(live_prices, "chart_quote", _chart)
    monkeypatch.setattr(live_prices.yf, "Ticker", lambda sym: sym)
    try:
        live_prices._fetch_raw("ADBE")
        live_prices._fetch_raw("ADBE")
    finally:
        live_prices.clear_quote_cache()

    assert calls == ["ADBE"]


def test_fetch_failure_is_isolated(monkeypatch):
    live_prices.clear_quote_cache()

    def _boom(_ticker):
        raise RuntimeError("429")

    monkeypatch.setattr(live_prices, "chart_quote", _boom)
    monkeypatch.setattr(live_prices.yf, "Ticker", lambda sym: sym)

    assert live_prices._fetch_raw("ADBE") is None


@pytest.mark.parametrize(
    ("currency", "scale", "expected"),
    [
        ("GBX", 0.01, "GBP"),  # pence factor applied: pounds
        ("GBX", 1.0, "GBX"),  # feed already in pounds per override, label stays the unit code
        ("GBP", 0.01, "GBP"),  # #6845: GBP metadata, pence feed, override
        ("USD", 1.0, "USD"),
    ],
)
def test_native_currency_label(monkeypatch, currency, scale, expected):
    monkeypatch.setattr(cache, "get_instrument_meta", lambda *_a, **_k: {"currency": currency})

    assert live_prices._native_currency("ABC", "L", scale) == expected
