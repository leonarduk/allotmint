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


def test_cache_only_fx_to_base_queues_a_stale_currency_and_uses_its_last_rate(fx_cache, no_live_fx):
    _seed_fx("USD", cache._last_close_target() - timedelta(days=10), rate=0.7)

    with cache.cache_only():
        rate = portfolio_utils._fx_to_base("USD", "GBP", {})

    assert rate == pytest.approx(0.7)
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

    assert rate == 1.0
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
