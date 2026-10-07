"""GET /instrument/allocation (#9974)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import instrument


def _client():
    app = FastAPI()
    app.include_router(instrument.router)
    return TestClient(app)


def test_allocation_route_returns_instrument_breakdown(monkeypatch):
    seen = []
    monkeypatch.setattr(
        instrument.look_through,
        "instrument_allocation",
        lambda ticker: seen.append(ticker) or {"ticker": ticker, "kind": "security"},
    )

    resp = _client().get("/instrument/allocation", params={"ticker": " minv.l "})

    assert resp.status_code == 200
    assert resp.json() == {"ticker": "MINV.L", "kind": "security"}
    assert seen == ["MINV.L"]


def test_allocation_route_rejects_malformed_ticker():
    assert _client().get("/instrument/allocation", params={"ticker": ".L"}).status_code == 400
