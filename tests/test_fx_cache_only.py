"""Cache-only FX for page requests that aggregate holdings (#8028).

#7917 made the timeseries FX conversion cache-only; these cover the other FX
path, ``portfolio_utils._fx_to_base``, and the aggregate portfolio routes that
call it, which must read cached FX rates rather than calling Yahoo.
"""

from datetime import timedelta

import pandas as pd
import pytest

import backend.utils.fx_rates as fx_rates
from backend.common import portfolio_utils
from backend.routes import portfolio as portfolio_routes
from backend.timeseries import cache, refresh_queue


def _explode(name):
    def fetch(*_args, **_kwargs):
        raise AssertionError(f"cache-only FX must not call {name}")

    return fetch


@pytest.fixture
def fx_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    return cache


@pytest.fixture
def no_live_fx(monkeypatch):
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _explode("fetch_fx_rate_range"))
    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", _explode("fetch_fx_rate_range_live"))


def _seed_fx(curr: str, last, rate: float) -> None:
    frame = pd.DataFrame({"Date": pd.bdate_range(end=last, periods=30), "Rate": rate})
    path = cache._fx_cache_path(curr)
    cache._ensure_local_dir(path)
    frame.to_parquet(path, index=False)


def test_cache_only_fx_to_base_uses_the_latest_cached_rate(fx_cache, no_live_fx):
    _seed_fx("USD", cache._last_close_target(), rate=0.75)

    with cache.cache_only():
        rate = portfolio_utils._fx_to_base("USD", "GBP", {})

    assert rate == pytest.approx(0.75)
    assert refresh_queue.pending() == []


def test_cache_only_fx_to_base_converts_to_a_non_gbp_base(fx_cache, no_live_fx):
    _seed_fx("USD", cache._last_close_target(), rate=0.75)

    with cache.cache_only():
        rate = portfolio_utils._fx_to_base("GBP", "USD", {})

    assert rate == pytest.approx(1 / 0.75)


def test_cache_only_fx_to_base_queues_a_stale_currency_once_and_uses_its_last_rate(fx_cache, no_live_fx):
    _seed_fx("USD", cache._last_close_target() - timedelta(days=10), rate=0.7)

    with cache.cache_only():
        rates = [portfolio_utils._fx_to_base("USD", "GBP", {}) for _ in range(3)]

    assert rates == [pytest.approx(0.7)] * 3
    assert refresh_queue.pending() == [("USD",)]


def test_cache_only_fx_to_base_falls_back_to_the_constant_and_queues_once(fx_cache, no_live_fx):
    """No FX cache file: the approximate constant, and one refresh queued however often it's asked."""
    with cache.cache_only():
        rates = [portfolio_utils._fx_to_base("USD", "GBP", {}) for _ in range(3)]

    assert rates == [pytest.approx(fx_rates.FALLBACK_RATES[("USD", "GBP")])] * 3
    assert refresh_queue.pending() == [("USD",)]


def test_cache_only_fx_to_base_ignores_invalid_currency_codes(fx_cache, no_live_fx):
    with cache.cache_only():
        rate = portfolio_utils._fx_to_base("NOT-A-CCY", "GBP", {})

    # No rate -- not a made-up 1.0 (#9664) -- and nothing queued.
    assert rate is None
    assert refresh_queue.pending() == []


def test_fx_to_base_outside_cache_only_still_fetches(fx_cache, monkeypatch):
    _seed_fx("USD", cache._last_close_target(), rate=0.75)
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", lambda *_: pd.DataFrame({"Rate": [0.8]}))

    assert portfolio_utils._fx_to_base("USD", "GBP", {}) == pytest.approx(0.8)


def test_queued_currency_refreshes_its_fx_cache(fx_cache, monkeypatch):
    refreshed = []
    monkeypatch.setattr(cache, "refresh_fx_cache", refreshed.append)
    monkeypatch.setattr(refresh_queue, "_refresh_one", _explode("_refresh_one"))

    assert refresh_queue.enqueue_fx("usd") is True
    assert refresh_queue.drain() == 1

    assert refreshed == ["USD"]
    # Within the retry cooldown the same currency is not queued again.
    assert refresh_queue.enqueue_fx("USD") is False


def test_enqueue_fx_rejects_invalid_currency_codes(fx_cache):
    assert refresh_queue.enqueue_fx("NOT-A-CCY") is False
    assert refresh_queue.enqueue_fx("") is False
    assert refresh_queue.pending() == []


def test_enqueue_fx_is_skipped_on_lambda(fx_cache, monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "fn")

    assert refresh_queue.enqueue_fx("USD") is False
    assert refresh_queue.pending() == []


@pytest.mark.parametrize(
    ("route", "aggregator", "kwargs"),
    [
        (portfolio_routes.group_instruments, "aggregate_by_ticker", {"owner": None, "account_type": None}),
        (portfolio_routes.group_sectors, "aggregate_by_sector", {}),
        (portfolio_routes.group_regions, "aggregate_by_region", {}),
    ],
)
def test_group_aggregate_routes_run_cache_only(monkeypatch, route, aggregator, kwargs):
    seen = []
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", lambda *_: {"accounts": []})
    monkeypatch.setattr(portfolio_utils, aggregator, lambda *_a, **_k: seen.append(cache.is_cache_only()) or [])

    route("all", as_of=None, **kwargs)

    assert seen == [True]
    assert cache.is_cache_only() is False


def test_owner_sectors_route_runs_cache_only(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(portfolio_routes, "resolve_accounts_root", lambda _req: tmp_path)
    monkeypatch.setattr(portfolio_routes, "resolve_owner_directory", lambda *_: None)
    monkeypatch.setattr(portfolio_routes.portfolio_mod, "build_owner_portfolio", lambda *_a, **_k: {"accounts": []})
    monkeypatch.setattr(
        portfolio_utils, "aggregate_by_sector", lambda *_a, **_k: seen.append(cache.is_cache_only()) or []
    )

    portfolio_routes.portfolio_sectors("alice", request=None, as_of=None)

    assert seen == [True]


@pytest.fixture
def usd_holding_without_changes(fx_cache, no_live_fx, monkeypatch):
    """A group with one USD holding whose snapshot lacks 7d/30d changes.

    Aggregating it reaches both live paths #8028 closes: ``_fx_to_base`` for
    the USD snapshot price, and ``price_change_pct`` -> ``load_meta_timeseries_range``
    for the missing changes. Every live price and FX source raises.
    """
    _seed_fx("USD", cache._last_close_target(), rate=0.75)
    # An earlier test's memoized AAPL.N read would skip the lookup (and its enqueue).
    cache._load_meta_timeseries_cached.cache_clear()
    cache._memoized_range_cached.cache_clear()
    monkeypatch.setattr(cache, "fetch_meta_timeseries", _explode("fetch_meta_timeseries"))
    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", _explode("cache.fetch_fx_rate_range_live"))
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"AAPL.N": {"last_price": 100.0, "price_currency": "USD"}})
    portfolio = {"accounts": [{"owner": "alice", "holdings": [{"ticker": "AAPL.N", "exchange": "N", "units": 2}]}]}
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", lambda *_: portfolio)


def test_group_instruments_prices_from_cached_fx_with_no_live_calls(usd_holding_without_changes):
    rows = portfolio_routes.group_instruments("all", owner=None, account_type=None, as_of=None)

    (row,) = rows
    assert row["last_price_gbp"] == pytest.approx(75.0)
    assert row["market_value_gbp"] == pytest.approx(150.0)
    assert row["change_7d_pct"] is None
    # No cached prices: the ticker is queued for the background refresh instead.
    assert ("AAPL", "N") in refresh_queue.pending()


@pytest.mark.parametrize("route", [portfolio_routes.group_sectors, portfolio_routes.group_regions])
def test_group_field_aggregates_make_no_live_calls(usd_holding_without_changes, route):
    (group,) = route("all", as_of=None)

    assert group["market_value_gbp"] == pytest.approx(150.0)


# ── #9664: no fabricated 1.0 rate, and the source of every rate reported ──


def test_cache_only_unknown_currency_with_no_cache_has_no_rate_and_is_queued(fx_cache, no_live_fx):
    """JPY has no approximate constant: an empty FX cache means no rate, never 1.0."""
    with cache.cache_only():
        rate = portfolio_utils._fx_to_base("JPY", "GBP", {})
        source = portfolio_utils.fx_rate_to_gbp_with_source("JPY")

    assert rate is None
    assert source == (None, fx_rates.FX_RATE_SOURCE_MISSING)
    assert refresh_queue.pending() == [("JPY",)]


@pytest.mark.parametrize(
    ("seed", "currency", "expected"),
    [
        (True, "USD", (0.75, fx_rates.FX_RATE_SOURCE_CACHE)),
        (False, "USD", (0.8, fx_rates.FX_RATE_SOURCE_FALLBACK)),
        (False, "JPY", (None, fx_rates.FX_RATE_SOURCE_MISSING)),
        (False, "GBP", (1.0, None)),
    ],
)
def test_cache_only_fx_rate_source(fx_cache, no_live_fx, seed, currency, expected):
    if seed:
        _seed_fx(currency, cache._last_close_target(), rate=0.75)

    with cache.cache_only():
        rate, source = portfolio_utils.fx_rate_to_gbp_with_source(currency)

    expected_rate, expected_source = expected
    assert source == expected_source
    assert rate == (None if expected_rate is None else pytest.approx(expected_rate))


def test_live_fx_rate_source_reports_live_and_tagged_fallback(fx_cache, monkeypatch):
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", lambda *_: pd.DataFrame({"Rate": [0.79]}))
    assert portfolio_utils.fx_rate_to_gbp_with_source("USD") == (pytest.approx(0.79), fx_rates.FX_RATE_SOURCE_LIVE)

    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", lambda *_: pd.DataFrame(columns=["Date", "Rate"]))
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", fx_rates.fetch_fx_rate_range)
    fx_rates.fetch_fx_rate_range.cache_clear()
    assert portfolio_utils.fx_rate_to_gbp_with_source("USD") == (0.8, fx_rates.FX_RATE_SOURCE_FALLBACK)
    assert portfolio_utils.fx_rate_to_gbp_with_source("JPY") == (None, fx_rates.FX_RATE_SOURCE_MISSING)


def test_fx_to_base_never_returns_one_on_failure(fx_cache, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", boom)
    for ccy in ("JPY", "CHF", "CAD", "AUD", "SGD"):
        assert portfolio_utils._fx_to_base(ccy, "GBP", {}) is None
    # A missing base leg is no rate either, not a 1.0 cross rate.
    assert portfolio_utils._fx_to_base("USD", "JPY", {}) is None


def test_cache_only_unknown_currency_series_is_left_detectably_unconverted(fx_cache, no_live_fx, monkeypatch):
    """No JPY rate: the series keeps its native close and gets no Close_gbp column."""
    monkeypatch.setattr(cache, "instrument_currency", lambda *_: "JPY")
    end = cache._last_close_target()
    df = pd.DataFrame({"Date": pd.bdate_range(end=end, periods=3), "Close": [1500.0, 1510.0, 1520.0]})

    with cache.cache_only():
        out = cache._convert_to_base_currency(df, "7203", "T", df["Date"].min().date(), end, "GBP")

    assert "Close_gbp" not in out.columns
    assert list(out["Close"]) == [1500.0, 1510.0, 1520.0]
    assert refresh_queue.pending() == [("7203", "T")]


def _enrich_in_currency(monkeypatch, currency: str, price: float = 10.0) -> dict:
    from backend.common import holding_utils, instrument_api
    from backend.common.constants import TICKER, UNITS

    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {"currency": currency})
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "N"))
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(holding_utils, "_get_dated_price_for_date_scaled", lambda *_a, **_k: (price, "cache", None))
    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", lambda *_a, **_k: (price, "cache"))
    monkeypatch.setattr(holding_utils, "get_effective_cost_basis_gbp", lambda *_a, **_k: 50.0)

    holding = {TICKER: "FOO.N", UNITS: 10}
    with cache.cache_only():
        return holding_utils.enrich_holding(holding, cache._last_close_target(), price_cache={})


@pytest.mark.parametrize(
    ("seed", "currency", "source"),
    [
        (True, "USD", fx_rates.FX_RATE_SOURCE_CACHE),
        (False, "USD", fx_rates.FX_RATE_SOURCE_FALLBACK),
        (False, "GBP", None),
        (False, "GBX", None),
    ],
)
def test_enriched_holding_reports_fx_rate_source(fx_cache, no_live_fx, monkeypatch, seed, currency, source):
    if seed:
        _seed_fx(currency, cache._last_close_target(), rate=0.75)

    enriched = _enrich_in_currency(monkeypatch, currency)

    assert enriched["fx_rate_source"] == source
    # The stubbed close stands for an already GBP-converted (pence-scaled for
    # GBX) Close_gbp, so 10 units x 10.0 is 100 GBP in every case.
    assert enriched["market_value_gbp"] == pytest.approx(100.0)


def test_enriched_holding_with_missing_fx_rate_is_unpriced(fx_cache, no_live_fx, monkeypatch):
    """A JPY holding with an empty FX cache is not valued at 1 JPY = 1 GBP (#9664)."""
    enriched = _enrich_in_currency(monkeypatch, "JPY", price=1500.0)

    assert enriched["fx_rate_source"] == fx_rates.FX_RATE_SOURCE_MISSING
    assert enriched["current_price_gbp"] is None
    assert enriched["market_value_gbp"] is None
    assert enriched["gain_gbp"] is None
    assert enriched["day_change_gbp"] is None
    assert ("JPY",) in refresh_queue.pending()
