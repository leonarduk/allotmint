from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.common.instrument_api as ia
from backend.routes import movers


def test_get_movers_success(monkeypatch):
    app = FastAPI()
    app.include_router(movers.router)

    def fake_top_movers(tickers, days, limit):
        assert tickers == ["AAA", "BBB"]
        assert days == 7
        assert limit == 5
        return {
            "gainers": [{"ticker": "AAA"}],
            "losers": [{"ticker": "BBB"}],
        }

    monkeypatch.setattr(ia, "top_movers", fake_top_movers)
    monkeypatch.setattr(movers, "top_movers", fake_top_movers)

    with TestClient(app) as client:
        resp = client.get("/movers?tickers=AAA,BBB&days=7&limit=5")
    assert resp.status_code == 200
    assert resp.json() == {
        "gainers": [{"ticker": "AAA"}],
        "losers": [{"ticker": "BBB"}],
    }


def test_get_movers_invalid_days(monkeypatch):
    app = FastAPI()
    app.include_router(movers.router)

    def fail_top_movers(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("top_movers should not be called")

    monkeypatch.setattr(ia, "top_movers", fail_top_movers)
    monkeypatch.setattr(movers, "top_movers", fail_top_movers)

    with TestClient(app) as client:
        resp = client.get("/movers?tickers=AAA&days=2")
    assert resp.status_code == 400


def test_get_movers_no_tickers(monkeypatch):
    app = FastAPI()
    app.include_router(movers.router)

    def fail_top_movers(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("top_movers should not be called")

    monkeypatch.setattr(ia, "top_movers", fail_top_movers)
    monkeypatch.setattr(movers, "top_movers", fail_top_movers)

    with TestClient(app) as client:
        resp = client.get("/movers?tickers= &days=7")
    assert resp.status_code == 400
