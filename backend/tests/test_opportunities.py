from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.opportunities import router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_opportunities_with_watchlist(monkeypatch):
    app = _build_app()

    monkeypatch.setattr(
        "backend.common.instrument_api.top_movers",
        lambda tickers, days, limit, min_weight=0.0, weights=None: {
            "gainers": [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "change_pct": 4.2,
                    "last_price_gbp": 100.0,
                    "last_price_date": "2024-01-01",
                }
            ],
            "losers": [
                {
                    "ticker": "BBB",
                    "name": "Beta",
                    "change_pct": -3.1,
                }
            ],
            "anomalies": ["ZZZ"],
        },
    )

    monkeypatch.setattr(
        "backend.agent.trading_agent.run",
        lambda notify=False: [
            {
                "ticker": "AAA",
                "action": "BUY",
                "reason": "Momentum",
                "confidence": 0.75,
            }
        ],
    )

    with TestClient(app) as client:
        resp = client.get("/opportunities", params={"tickers": "AAA,BBB", "days": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert {entry["ticker"] for entry in data["entries"]} == {"AAA", "BBB"}
    assert data["entries"][0]["signal"]["ticker"] == "AAA"
    assert data["context"]["source"] == "watchlist"
    assert data["context"]["anomalies"] == ["ZZZ"]
    assert data["signals"][0]["action"] == "BUY"


def test_opportunities_requires_auth_for_group(monkeypatch):
    app = _build_app()

    with TestClient(app) as client:
        resp = client.get("/opportunities", params={"group": "all"})
    assert resp.status_code == 401


def test_opportunities_with_group(monkeypatch):
    app = _build_app()

    monkeypatch.setattr("backend.routes.opportunities.decode_token", lambda token: "alice")

    monkeypatch.setattr(
        "backend.common.instrument_api.instrument_summaries_for_group",
        lambda slug: [
            {"ticker": "AAA", "market_value_gbp": 1000.0, "name": "Alpha"},
            {"ticker": "BBB", "market_value_gbp": 500.0, "name": "Beta"},
        ],
    )

    monkeypatch.setattr(
        "backend.common.instrument_api.top_movers",
        lambda tickers, days, limit, min_weight=0.0, weights=None: {
            "gainers": [
                {"ticker": "AAA", "name": "Alpha", "change_pct": 2.0, "market_value_gbp": 1000.0}
            ],
            "losers": [
                {"ticker": "BBB", "name": "Beta", "change_pct": -1.0, "market_value_gbp": 500.0}
            ],
            "anomalies": [],
        },
    )

    monkeypatch.setattr("backend.agent.trading_agent.run", lambda notify=False: [])

    headers = {"Authorization": "Bearer token"}
    with TestClient(app) as client:
        resp = client.get(
            "/opportunities",
            params={"group": "all", "days": 1, "limit": 5},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["context"]["source"] == "group"
    assert {entry["ticker"] for entry in data["entries"]} == {"AAA", "BBB"}
