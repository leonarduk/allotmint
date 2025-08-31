import pytest
from fastapi.testclient import TestClient

import backend.common.instrument_api as ia
from backend.local_api.main import app

client = TestClient(app)
token = client.post("/token", data={"username": "testuser", "password": "password"}).json()["access_token"]
client.headers.update({"Authorization": f"Bearer {token}"})


def test_group_movers_endpoint(monkeypatch):
    def fake_summaries(slug: str):
        assert slug == "demo"
        return [
            {"ticker": "AAA", "market_value_gbp": 100.0},
            {"ticker": "BBB", "market_value_gbp": 50.0},
            {"ticker": "CCC", "market_value_gbp": 25.0},
        ]

    def fake_top_movers(tickers, days, limit, *, min_weight, weights):
        assert tickers == ["AAA", "BBB", "CCC"]
        assert days == 7
        assert limit == 5
        assert min_weight == 0.5
        total = 100.0 + 50.0 + 25.0
        assert weights["AAA"] == pytest.approx(100.0 / total * 100)
        assert weights["BBB"] == pytest.approx(50.0 / total * 100)
        assert weights["CCC"] == pytest.approx(25.0 / total * 100)
        return {
            "gainers": [{"ticker": "AAA", "name": "AAA", "change_pct": 5}],
            "losers": [{"ticker": "BBB", "name": "BBB", "change_pct": -3}],
        }

    monkeypatch.setattr(ia, "instrument_summaries_for_group", fake_summaries)
    monkeypatch.setattr(ia, "top_movers", fake_top_movers)

    resp = client.get("/portfolio-group/demo/movers?days=7&limit=5&min_weight=0.5")
    assert resp.status_code == 200
    data = resp.json()
    assert [g["ticker"] for g in data["gainers"]] == ["AAA"]
    assert [loser["ticker"] for loser in data["losers"]] == ["BBB"]
    assert data["gainers"][0]["market_value_gbp"] == 100.0
    assert data["losers"][0]["market_value_gbp"] == 50.0


def test_group_movers_endpoint_empty(monkeypatch):
    def fake_summaries(slug: str):
        assert slug == "demo"
        return []

    monkeypatch.setattr(ia, "instrument_summaries_for_group", fake_summaries)

    resp = client.get("/portfolio-group/demo/movers")
    assert resp.status_code == 200
    assert resp.json() == {"gainers": [], "losers": []}
