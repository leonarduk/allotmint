"""Tests for the `/opportunities` endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import opportunities as opportunities_mod


@pytest.fixture()
def client() -> TestClient:
    """Return a test client with the opportunities router mounted."""

    app = FastAPI()
    app.include_router(opportunities_mod.router)
    with TestClient(app) as client:
        yield client


def test_watchlist_sorts_by_abs_change_and_preserves_anomalies(monkeypatch, client):
    """Watchlist responses should be sorted by absolute change and keep anomalies."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})

    monkeypatch.setattr(
        opportunities_mod.instrument_api,
        "top_movers",
        lambda tickers, days, limit, min_weight=0.0, weights=None: {
            "gainers": [
                {"ticker": "ABC", "name": "Alpha", "change_pct": 1.0},
                {"ticker": "GHI", "name": "Gamma", "change_pct": 0.25},
            ],
            "losers": [
                {"ticker": "DEF", "name": "Delta", "change_pct": -5.0},
            ],
            "anomalies": ["XYZ"],
        },
    )

    monkeypatch.setattr(
        opportunities_mod.trading_agent,
        "run",
        lambda tickers, notify=False: [
            {
                "ticker": "DEF",
                "action": "SELL",
                "reason": "Stop loss",
                "confidence": 0.85,
            },
        ],
    )

    response = client.get(
        "/opportunities",
        params={"tickers": "ABC, DEF", "days": 1, "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    # Sorted by absolute change percentage so the 5% loss comes first.
    assert [entry["ticker"] for entry in body["entries"]] == ["DEF", "ABC", "GHI"]
    assert body["entries"][0]["signal"]["action"] == "SELL"
    assert body["context"]["source"] == "watchlist"
    assert body["context"]["anomalies"] == ["XYZ"]
    # Authentication is optional for watchlists, so no signals around 401.
    assert "detail" not in body


def test_watchlist_forwards_instrument_type(monkeypatch, client):
    """`/opportunities` entries must carry the `instrument_type` returned by top_movers.

    Regression test for the gap where `OpportunityEntry(...)` was constructed
    from `row` without copying `row.get("instrument_type")`, so the field
    always fell back to its `None` default even though `top_movers()`
    returned a populated value. See allotmint#6902 review discussion.
    """

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})

    monkeypatch.setattr(
        opportunities_mod.instrument_api,
        "top_movers",
        lambda tickers, days, limit, min_weight=0.0, weights=None: {
            "gainers": [
                {"ticker": "ABC", "name": "Alpha", "change_pct": 1.0, "instrument_type": "ETF"},
            ],
            "losers": [
                {"ticker": "DEF", "name": "Delta", "change_pct": -5.0, "instrument_type": None},
            ],
            "anomalies": [],
        },
    )

    monkeypatch.setattr(
        opportunities_mod.trading_agent,
        "run",
        lambda tickers, notify=False: [],
    )

    response = client.get(
        "/opportunities",
        params={"tickers": "ABC, DEF", "days": 1, "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    entries_by_ticker = {entry["ticker"]: entry for entry in body["entries"]}
    assert entries_by_ticker["ABC"]["instrument_type"] == "ETF"
    assert entries_by_ticker["DEF"]["instrument_type"] is None


def test_group_requires_token_when_auth_enabled(monkeypatch, client):
    """Groups should enforce authentication when auth is not disabled."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})
    monkeypatch.setattr(opportunities_mod.config, "disable_auth", False, raising=False)

    response = client.get("/opportunities", params={"group": "growth", "days": 1})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_group_rejects_invalid_token(monkeypatch, client):
    """A provided token that fails validation should return HTTP 401."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})
    monkeypatch.setattr(opportunities_mod.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(opportunities_mod, "decode_token", lambda token: None)

    response = client.get(
        "/opportunities",
        params={"group": "growth", "days": 1},
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"


def test_group_allowed_for_demo_request_regardless_of_token(monkeypatch, client):
    """A demo-scoped request must be let through even when it carries no
    token decode_token() would ever accept.

    Regression test: backend.bootstrap.middleware.demo_scope_gate resolves
    demo identity (is_demo_request()) unconditionally, for every request,
    before any route handler runs -- but this endpoint's own auth check
    (added before the demo-link feature existed) called decode_token(token)
    directly. decode_token() deliberately returns None for a demo-scoped
    token (backend/auth.py:255-256, the control that keeps a demo token from
    ever being mistaken for a real login), so a valid, already-authorized
    demo request was rejected here with 401 -- confirmed live: it broke the
    Movers page ("Portfolio" watchlist) for the buffett demo account and
    logged the whole demo session out (the frontend treats any 401 as
    "session expired", see api.ts's UNAUTHORIZED_EVENT). Checking
    is_demo_request() first, mirroring ensure_owner_access, fixes it without
    weakening the real-token path below (test_group_rejects_invalid_token
    still covers that with is_demo_request left False)."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})
    monkeypatch.setattr(opportunities_mod.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(opportunities_mod, "is_demo_request", lambda: True)
    # No Authorization header at all, and decode_token would reject anything
    # presented -- is_demo_request() alone must be enough to authorize this.
    monkeypatch.setattr(opportunities_mod, "decode_token", lambda token: None)
    monkeypatch.setattr(
        opportunities_mod,
        "_group_opportunities",
        lambda slug, *, days, limit, min_weight: {"gainers": [], "losers": [], "anomalies": []},
    )

    response = client.get("/opportunities", params={"group": "all", "days": 1})

    assert response.status_code == 200
    assert response.json()["context"]["group"] == "all"


def test_group_success_decorates_signals(monkeypatch, client):
    """Successful group calls should decorate entries with trading signals."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})
    monkeypatch.setattr(opportunities_mod, "decode_token", lambda token: {"sub": "alice"})

    captured = {}

    def fake_group(slug: str, *, days: int, limit: int, min_weight: float):
        captured["args"] = (slug,)
        captured["kwargs"] = {"days": days, "limit": limit, "min_weight": min_weight}
        return {
            "gainers": [{"ticker": "XYZ", "name": "Example", "change_pct": 2.5}],
            "losers": [{"ticker": "ABC", "name": "Acme", "change_pct": -1.2}],
            "anomalies": ["HALT"],
        }

    monkeypatch.setattr(opportunities_mod, "_group_opportunities", fake_group)

    signal_tickers = []

    def fake_signals(tickers, *, notify=False):
        signal_tickers.extend(tickers)
        return [
            {
                "ticker": "xyz",
                "action": "BUY",
                "reason": "Breakout",
                "confidence": 0.6,
            }
        ]

    monkeypatch.setattr(
        opportunities_mod.trading_agent,
        "run",
        fake_signals,
    )

    response = client.get(
        "/opportunities",
        params={"group": "growth", "days": 1, "limit": 5, "min_weight": 1.5},
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 200
    body = response.json()
    assert captured == {
        "args": ("growth",),
        "kwargs": {"days": 1, "limit": 5, "min_weight": 1.5},
    }
    assert [entry["ticker"] for entry in body["entries"]] == ["XYZ", "ABC"]
    assert body["entries"][0]["signal"]["action"] == "BUY"
    assert body["context"]["anomalies"] == ["HALT"]
    assert signal_tickers == ["ABC", "XYZ"]


def test_invalid_days_rejected(monkeypatch, client):
    """Requests using unsupported day windows should return HTTP 400."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1, 7})

    response = client.get("/opportunities", params={"tickers": "ABC", "days": 3})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid days"


def test_empty_tickers_rejected(monkeypatch, client):
    """Watchlist requests require at least one ticker symbol."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})

    response = client.get(
        "/opportunities",
        params={"tickers": "  ,  ", "days": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "No tickers provided"


def test_empty_mover_result_skips_signal_generation(monkeypatch, client):
    """No movers must not trigger the agent's empty-list all-ticker fallback."""

    monkeypatch.setattr(opportunities_mod, "_PORTFOLIO_ALLOWED_DAYS", {1})
    monkeypatch.setattr(
        opportunities_mod.instrument_api,
        "top_movers",
        lambda *args, **kwargs: {"gainers": [], "losers": [], "anomalies": []},
    )

    def unexpected_signal_generation(*args, **kwargs):
        pytest.fail("trading agent should not run without mover tickers")

    monkeypatch.setattr(
        opportunities_mod.trading_agent,
        "run",
        unexpected_signal_generation,
    )

    response = client.get(
        "/opportunities",
        params={"tickers": "ABC", "days": 1},
    )

    assert response.status_code == 200
    assert response.json()["entries"] == []
    assert response.json()["signals"] == []
