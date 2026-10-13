"""Tests for the shared performance inputs (``portfolio_cache.memoised``, #10755).

The Performance page requests alpha, tracking error, max drawdown, the value
history, TWR and XIRR in parallel. Each used to rebuild the owner portfolio,
price the holdings and replay the ledger for itself, which on a cold cache ran
the set past the client's 30s timeout. These tests pin that the routes now
share those builds, that concurrent misses run one build, and that nothing is
cached outside the routes.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import portfolio_cache, portfolio_utils
from backend.routes import performance
from backend.utils.pricing_dates import PricingDateCalculator


def test_memoised_builds_every_time_outside_the_sharing_block():
    builds: list[int] = []

    for _ in range(2):
        portfolio_cache.memoised(("k",), lambda: builds.append(1) or "value")

    assert len(builds) == 2


def test_memoised_shares_one_build_per_key_inside_the_sharing_block():
    builds: list[str] = []

    with portfolio_cache.sharing_performance_inputs():
        first = portfolio_cache.memoised(("k", 1), lambda: builds.append("a") or {"v": 1})
        again = portfolio_cache.memoised(("k", 1), lambda: builds.append("b") or {"v": 2})
        other = portfolio_cache.memoised(("k", 2), lambda: builds.append("c") or {"v": 3})

    assert builds == ["a", "c"]
    assert first == again == {"v": 1}
    assert other == {"v": 3}


def test_concurrent_misses_wait_for_one_build():
    builds: list[int] = []
    release = threading.Event()

    def slow_build():
        builds.append(1)
        release.wait(timeout=5)
        return "history"

    def request():
        with portfolio_cache.sharing_performance_inputs():
            return portfolio_cache.memoised(("history", "alice"), slow_build)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(request) for _ in range(6)]
        # Give the other requests time to reach the cache while the leader builds.
        time.sleep(0.2)
        release.set()
        results = [f.result(timeout=5) for f in futures]

    assert results == ["history"] * 6
    assert len(builds) == 1


def test_account_writes_invalidate_the_shared_inputs():
    builds: list[int] = []

    with portfolio_cache.sharing_performance_inputs():
        portfolio_cache.memoised(("k",), lambda: builds.append(1))
        portfolio_cache.invalidate_group_portfolios()
        portfolio_cache.memoised(("k",), lambda: builds.append(1))

    assert len(builds) == 2


@pytest.fixture
def counting_builds(monkeypatch):
    """Stub the three expensive builds behind the owner metrics and count each call."""

    calls: dict[str, list] = {"portfolio": [], "prices": [], "ledger": []}
    reporting_date = PricingDateCalculator().reporting_date
    days = pd.bdate_range(end=reporting_date, periods=30)
    closes = pd.Series([100.0 + i for i in range(len(days))], index=[d.date() for d in days])

    def build_owner_portfolio(owner, **_kwargs):
        calls["portfolio"].append(owner)
        return {"owner": owner, "accounts": [{"holdings": [{"ticker": "AAA.L", "exchange": "L", "units": 10}]}]}

    def price_gbp_holding_values(holdings, effective_days, window, *, total_return):
        calls["prices"].append(total_return)
        return [(closes * 10, "price")], [], []

    def ledger_performance_for(owner, pricing_date):
        calls["ledger"].append(owner)
        return None  # no ledger: TWR/XIRR fall back to the value series

    monkeypatch.setattr(portfolio_utils.portfolio_mod, "build_owner_portfolio", build_owner_portfolio)
    monkeypatch.setattr(portfolio_utils, "_price_gbp_holding_values", price_gbp_holding_values)
    monkeypatch.setattr(portfolio_utils, "_ledger_performance_for", ledger_performance_for)
    monkeypatch.setattr(portfolio_utils, "load_transactions", lambda owner: [])
    bench = pd.Series(0.001, index=[d.date() for d in days[1:]])
    monkeypatch.setattr(portfolio_utils, "_benchmark_daily_returns", lambda *_a: (bench, "price"))
    return calls


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(performance.router)
    return TestClient(app)


OWNER_METRIC_PATHS = (
    "/performance/alice/alpha",
    "/performance/alice/tracking-error",
    "/performance/alice/max-drawdown",
    "/performance/alice",
    "/performance/alice/twr",
    "/performance/alice/xirr",
)


def test_owner_metric_routes_share_one_build_of_each_input(counting_builds):
    client = _client()

    for path in OWNER_METRIC_PATHS:
        assert client.get(path).status_code == 200, path

    assert counting_builds["portfolio"] == ["alice"]
    # One total-return pass (alpha + tracking error), one price pass (the rest).
    assert sorted(counting_builds["prices"]) == [False, True]
    assert counting_builds["ledger"] == ["alice"]


def test_parallel_owner_metric_requests_share_one_build_of_each_input(counting_builds):
    client = _client()

    with ThreadPoolExecutor(max_workers=len(OWNER_METRIC_PATHS)) as pool:
        statuses = list(pool.map(lambda path: client.get(path).status_code, OWNER_METRIC_PATHS))

    assert statuses == [200] * len(OWNER_METRIC_PATHS)
    assert counting_builds["portfolio"] == ["alice"]
    assert sorted(counting_builds["prices"]) == [False, True]
    assert counting_builds["ledger"] == ["alice"]


def test_different_windows_share_the_ledger_rebuild_but_not_the_pricing(counting_builds):
    client = _client()

    client.get("/performance/alice/twr", params={"days": 365})
    client.get("/performance/alice/twr", params={"days": 90})

    assert counting_builds["ledger"] == ["alice"]
    assert counting_builds["prices"] == [False, False]


def test_direct_calls_outside_the_routes_are_not_cached(counting_builds):
    portfolio_utils.compute_max_drawdown("alice", 365)
    portfolio_utils.compute_max_drawdown("alice", 365)

    assert counting_builds["portfolio"] == ["alice", "alice"]
    assert counting_builds["prices"] == [False, False]


def test_a_failed_build_is_not_cached(monkeypatch):
    calls: list[str] = []

    def unknown_group(slug, **_kwargs):
        calls.append(slug)
        raise ValueError(slug)

    monkeypatch.setattr(portfolio_utils.group_portfolio, "build_group_portfolio", unknown_group)
    client = _client()

    assert client.get("/performance-group/ghosts/max-drawdown").status_code == 404
    assert client.get("/performance-group/ghosts/max-drawdown").status_code == 404
    assert calls == ["ghosts", "ghosts"]


def test_as_of_requests_do_not_share_todays_inputs(counting_builds):
    client = _client()
    as_of = (PricingDateCalculator().reporting_date - timedelta(days=7)).isoformat()

    client.get("/performance/alice/max-drawdown")
    client.get("/performance/alice/max-drawdown", params={"as_of": as_of})

    assert len(counting_builds["portfolio"]) == 2
