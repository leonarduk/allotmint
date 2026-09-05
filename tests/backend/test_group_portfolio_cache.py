"""Tests for the group-portfolio cache (``backend/common/portfolio_cache.py``).

Covers the two things the cache has to get right: it must actually stop the
repeated multi-second build (#7215), and it must never serve one caller's
portfolio to a caller with a different scope -- the leak #7402 closed.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import portfolio_cache
from backend.common.ttl_cache import TTLCache
from backend.routes import portfolio


def _client():
    app = FastAPI()
    app.include_router(portfolio.router)
    return TestClient(app)


def _portfolio_for(owners):
    return {
        "slug": "all",
        "name": "At a glance",
        "members": list(owners),
        "as_of": "2024-01-01",
        "accounts": [{"account_type": "ISA", "owner": owner, "holdings": []} for owner in owners],
    }


@pytest.fixture
def counting_builder(monkeypatch):
    """Stub ``build_group_portfolio`` and record every call it receives."""

    calls: list[str] = []

    def _build(slug, **_kwargs):
        calls.append(slug)
        return _portfolio_for(["alice", "bob"])

    monkeypatch.setattr(portfolio.group_portfolio, "build_group_portfolio", _build)
    return calls


def test_repeat_requests_share_one_build(counting_builder):
    client = _client()

    for _ in range(3):
        assert client.get("/portfolio-group/all").status_code == 200

    assert len(counting_builder) == 1


def test_sibling_endpoints_share_one_build(counting_builder, monkeypatch):
    monkeypatch.setattr(portfolio.portfolio_utils, "aggregate_by_ticker", lambda data: [])
    monkeypatch.setattr(portfolio.portfolio_utils, "aggregate_by_sector", lambda data: [])
    monkeypatch.setattr(portfolio.portfolio_utils, "aggregate_by_region", lambda data: [])
    client = _client()

    for path in (
        "/portfolio-group/all",
        "/portfolio-group/all/instruments",
        "/portfolio-group/all/sectors",
        "/portfolio-group/all/regions",
    ):
        assert client.get(path).status_code == 200

    # One page load touches all four; before the cache that was four builds.
    assert len(counting_builder) == 1


def test_distinct_slugs_and_as_of_do_not_share_an_entry(counting_builder):
    client = _client()

    client.get("/portfolio-group/all")
    client.get("/portfolio-group/adults")
    client.get("/portfolio-group/all", params={"as_of": "2024-01-15"})
    client.get("/portfolio-group/all")

    # Three distinct keys, and the fourth request repeats the first.
    assert counting_builder == ["all", "adults", "all"]


def test_demo_scoped_request_never_reads_an_unscoped_entry(monkeypatch):
    """A demo-link visitor must not be served the full-owner portfolio.

    ``build_group_portfolio`` reaches ``list_plots``, which narrows to the
    configured demo owner when ``is_demo_request()`` is true. Keying the cache
    on ``(slug, as_of)`` alone would hand a demo visitor whatever an
    authenticated request cached first -- every owner's holdings, which is
    exactly what #7402 fixed.
    """

    demo_flag = {"value": False}
    monkeypatch.setattr(portfolio_cache, "_demo_scope", lambda: "demo-owner" if demo_flag["value"] else None)

    def _build(slug, **_kwargs):
        # Mirrors list_plots' own narrowing.
        owners = ["demo-owner"] if demo_flag["value"] else ["alice", "bob"]
        return _portfolio_for(owners)

    monkeypatch.setattr(portfolio.group_portfolio, "build_group_portfolio", _build)
    client = _client()

    # Warm the cache as a normal request, then ask again as a demo request.
    assert client.get("/portfolio-group/all").json()["members"] == ["alice", "bob"]

    demo_flag["value"] = True
    assert client.get("/portfolio-group/all").json()["members"] == ["demo-owner"]

    # ...and back the other way: the demo entry must not answer a normal request.
    demo_flag["value"] = False
    assert client.get("/portfolio-group/all").json()["members"] == ["alice", "bob"]


def test_price_refresh_invalidates(monkeypatch, counting_builder):
    monkeypatch.setattr(portfolio.prices, "refresh_prices", lambda: {"tickers": 0})
    client = _client()

    client.get("/portfolio-group/all")
    assert len(counting_builder) == 1

    assert client.post("/prices/refresh").status_code == 200

    client.get("/portfolio-group/all")
    assert len(counting_builder) == 2


def test_cached_payload_is_isolated_from_caller_mutation(counting_builder):
    """A caller mutating what it got back must not corrupt the cached copy."""

    first = portfolio_cache.cached_group_portfolio("all", None, lambda: _portfolio_for(["alice"]))
    first["accounts"].append({"account_type": "SIPP", "owner": "mallory", "holdings": []})
    first["name"] = "tampered"

    second = portfolio_cache.cached_group_portfolio("all", None, lambda: _portfolio_for(["alice"]))
    assert second["name"] == "At a glance"
    assert [a["owner"] for a in second["accounts"]] == ["alice"]


class TestTTLCache:
    def test_builds_once_within_the_ttl_and_again_after_it(self):
        cache: TTLCache[int] = TTLCache(ttl_seconds=60.0)
        calls = []

        def _build():
            calls.append(1)
            return len(calls)

        assert cache.get_or_build(("k",), _build) == 1
        assert cache.get_or_build(("k",), _build) == 1
        assert len(calls) == 1

        # Expire without sleeping: a zero TTL is never fresh.
        expired: TTLCache[int] = TTLCache(ttl_seconds=0.0)
        assert expired.get_or_build(("k",), _build) == 2
        assert expired.get_or_build(("k",), _build) == 3

    def test_clear_drops_every_entry(self):
        cache: TTLCache[int] = TTLCache(ttl_seconds=60.0)
        cache.get_or_build(("a",), lambda: 1)
        cache.get_or_build(("b",), lambda: 2)
        assert len(cache) == 2

        cache.clear()
        assert len(cache) == 0

    def test_a_failed_build_is_not_cached(self):
        cache: TTLCache[int] = TTLCache(ttl_seconds=60.0)

        with pytest.raises(RuntimeError):
            cache.get_or_build(("k",), lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        assert len(cache) == 0
        assert cache.get_or_build(("k",), lambda: 7) == 7


def test_cache_key_includes_pricing_date_and_demo_scope(monkeypatch):
    monkeypatch.setattr(portfolio_cache, "_demo_scope", lambda: None)
    assert portfolio_cache.group_portfolio_cache_key("all", None) == ("all", None, None)
    assert portfolio_cache.group_portfolio_cache_key("all", dt.date(2024, 1, 15)) == ("all", "2024-01-15", None)

    monkeypatch.setattr(portfolio_cache, "_demo_scope", lambda: "buffett")
    assert portfolio_cache.group_portfolio_cache_key("all", None) == ("all", None, "buffett")
