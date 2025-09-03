import backend.common.instrument_api as ia
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    from backend.routes.movers import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_movers_success(monkeypatch):
    def fake_top_movers(tickers, days, limit):
        assert tickers == ["AAA", "BBB"]
        assert days == 7
        assert limit == 5
        return {
            "gainers": [{"ticker": "AAA", "name": "AAA", "change_pct": 5}],
            "losers": [{"ticker": "BBB", "name": "BBB", "change_pct": -3}],
        }

    from backend.routes import movers

    monkeypatch.setattr(ia, "top_movers", fake_top_movers)
    monkeypatch.setattr(movers, "top_movers", fake_top_movers)

    client = _client()
    resp = client.get("/movers?tickers=AAA,BBB&days=7&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert [g["ticker"] for g in data["gainers"]] == ["AAA"]
    assert [l["ticker"] for l in data["losers"]] == ["BBB"]


def test_movers_invalid_days():
    client = _client()
    resp = client.get("/movers?tickers=AAA&days=2")
    assert resp.status_code == 400
