"""Tests for the `/opportunities` endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

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
        lambda notify=False: [
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

    monkeypatch.setattr(
        opportunities_mod.trading_agent,
        "run",
        lambda notify=False: [
            {
                "ticker": "xyz",
                "action": "BUY",
                "reason": "Breakout",
                "confidence": 0.6,
            }
        ],
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
