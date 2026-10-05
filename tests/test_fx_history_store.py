"""The FX cache as the canonical 2007+ FX history store (#9322).

Covers the configurable history start and backfill, the reference currencies
the scheduled refresh always keeps, the no-fetch ``load_fx_history`` reader,
and serving the synthetic ``{CCY}GBP.FX`` instruments from the same store.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from backend.timeseries import cache, refresh_queue


@pytest.fixture
def fx_store(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.setattr(cache.config, "fx_history_start", None)
    monkeypatch.setattr(cache.config, "fx_reference_currencies", None)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    monkeypatch.setattr(cache, "_FX_BACKFILL_TRIED", set())
    return tmp_path


@pytest.fixture
def live(monkeypatch):
    """Fake Yahoo: business-day rates of 0.5 for any requested window, recording each request."""
    requested = []

    def fake_live(base, quote, start, end):
        requested.append((base, quote, start, end))
        return pd.DataFrame({"Date": pd.bdate_range(start, end).date, "Rate": 0.5})

    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", fake_live)
    return requested


def _seed(curr: str, first: date, last: date, rate: float = 0.8) -> None:
    frame = pd.DataFrame({"Date": pd.bdate_range(first, last), "Rate": rate})
    path = cache._fx_cache_path(curr)
    cache._ensure_local_dir(path)
    frame.to_parquet(path, index=False)


def test_history_start_defaults_to_2007_and_is_configurable(fx_store, monkeypatch):
    assert cache.fx_history_start() == date(2007, 1, 1)
    monkeypatch.setattr(cache.config, "fx_history_start", "2005-03-01")
    assert cache.fx_history_start() == date(2005, 3, 1)
    monkeypatch.setattr(cache.config, "fx_history_start", "not-a-date")
    assert cache.fx_history_start() == date(2007, 1, 1)


def test_new_currency_is_seeded_from_the_history_start(fx_store, live):
    assert cache.refresh_fx_cache("EUR") is True

    # Up to the last completed weekday: today's rate is still moving.
    assert live == [("EUR", "GBP", date(2007, 1, 1), cache._last_close_target())]
    stored = cache.load_fx_history("EUR")
    assert stored["Date"].min().date() <= date(2007, 1, 2)


def test_short_history_is_backfilled_once_without_rewriting_stored_rates(fx_store, live):
    today = date.today()
    _seed("USD", today - timedelta(days=3650), today)
    first = cache.load_fx_history("USD")["Date"].min().date()
    cache._FX_FRAMES.clear()

    assert cache.refresh_fx_cache("USD") is True

    assert live[-1] == ("USD", "GBP", date(2007, 1, 1), first - timedelta(days=1))
    stored = cache.load_fx_history("USD")
    assert stored["Date"].min().date() <= date(2007, 1, 2)
    assert stored["Date"].is_monotonic_increasing and not stored["Date"].duplicated().any()
    # Rates already stored keep their values; only the gap took the fetched 0.5.
    assert (stored.loc[stored["Date"].dt.date >= first, "Rate"] == 0.8).all()
    assert (stored.loc[stored["Date"].dt.date < first, "Rate"] == 0.5).all()

    # Already back to the start: a later refresh asks for nothing before it.
    live.clear()
    cache.refresh_fx_cache("USD")
    assert all(start > date(2007, 1, 1) for _b, _q, start, _e in live)


def test_backfill_with_no_earlier_data_is_not_retried_in_the_same_process(fx_store, monkeypatch):
    today = date.today()
    _seed("CAD", date(2016, 1, 4), today)
    requested = []

    def nothing(base, quote, start, end):
        requested.append(start)
        return pd.DataFrame(columns=["Date", "Rate"])

    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", nothing)

    assert cache.refresh_fx_cache("CAD") is False
    assert cache.refresh_fx_cache("CAD") is False
    assert requested.count(date(2007, 1, 1)) == 1


def test_refresh_for_tickers_always_includes_the_reference_currencies(fx_store, live, monkeypatch):
    monkeypatch.setattr(cache, "get_instrument_meta", lambda full: {"currency": "JPY"})

    cache.refresh_fx_cache_for_tickers(["7203.T"])

    assert sorted(base for base, *_ in live) == ["CAD", "EUR", "JPY", "USD"]

    live.clear()
    monkeypatch.setattr(cache.config, "fx_reference_currencies", [])
    monkeypatch.setattr(cache, "_FX_BACKFILL_TRIED", set())
    cache.refresh_fx_cache_for_tickers([])
    assert live == []


def test_load_fx_history_reads_the_store_without_fetching(fx_store, monkeypatch):
    _seed("USD", date(2008, 1, 1), date(2008, 1, 31), rate=0.5)
    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", lambda *_a: pytest.fail("load_fx_history fetched"))

    window = cache.load_fx_history("usd", start=date(2008, 1, 2), end=date(2008, 1, 3))

    assert window["Date"].dt.date.tolist() == [date(2008, 1, 2), date(2008, 1, 3)]
    assert window["Rate"].tolist() == [0.5, 0.5]
    assert cache.load_fx_history("USD", start=date.min, end=date.max)["Rate"].count() == 23
    assert cache.load_fx_history("EUR").empty
    assert cache.load_fx_history("GBP").empty
    assert cache.load_fx_history("NOT-A-CCY").empty


def test_fx_instrument_is_served_from_the_fx_store(fx_store, monkeypatch):
    """``USDGBP.FX`` (the frontend's currency link) reads the canonical store, not a meta parquet."""
    last = cache._last_close_target()
    _seed("USD", last - timedelta(days=60), last, rate=0.79)
    monkeypatch.setattr(cache, "fetch_meta_timeseries", lambda *_a, **_k: pytest.fail("fetched a meta series"))

    df = cache.load_meta_timeseries_range("USDGBP", "FX", last - timedelta(days=10), last)

    assert not df.empty
    assert (df["Close"] == 0.79).all() and (df["Open"] == 0.79).all()
    assert set(df["Ticker"]) == {"USDGBP"}
    assert not (fx_store / "meta" / "USDGBP_FX.parquet").exists()

    rolling = cache.load_meta_timeseries("USDGBP", "FX", 30)
    assert not rolling.empty and rolling["Date"].max().date() == last

    with cache.cache_only():
        cached = cache.load_meta_timeseries_range("USDGBP", "FX", last - timedelta(days=5), last)
    assert not cached.empty and cached["Close"].iloc[-1] == pytest.approx(0.79)
    assert refresh_queue.pending() == []


def test_stale_fx_instrument_queues_an_fx_refresh(fx_store):
    last = cache._last_close_target() - timedelta(days=10)
    _seed("EUR", last - timedelta(days=30), last, rate=0.86)

    df = cache.load_meta_timeseries_range("EURGBP", "FX", last - timedelta(days=5), cache._last_close_target())

    assert df["Close"].iloc[-1] == pytest.approx(0.86)
    assert refresh_queue.pending() == [("EUR",)]


@pytest.mark.parametrize(
    ("ticker", "exchange"), [("GBPUSD", "FX"), ("USDEUR", "FX"), ("USDGBP", "L"), ("GBPGBP", "FX")]
)
def test_only_ccy_gbp_fx_instruments_are_rerouted(ticker, exchange):
    assert cache._fx_instrument_currency(ticker, exchange) is None
