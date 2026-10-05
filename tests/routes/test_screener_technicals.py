"""/screener/technicals: the allotmint-pro technical indicators for one instrument.

Uses a stand-in for ``instrument_technicals`` so it runs with or without the private
package installed.
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import core_feature_unavailable_handler
from backend.common.core_optional import CoreFeatureUnavailableError
from backend.routes import screener


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(screener.router)
    app.add_exception_handler(CoreFeatureUnavailableError, core_feature_unavailable_handler)
    return TestClient(app)


def test_technicals_returns_402_without_the_pro_module(monkeypatch):
    monkeypatch.setattr(screener, "instrument_technicals", None)

    resp = _client().get("/screener/technicals", params={"ticker": "ADBE.N"})

    assert resp.status_code == 402
    assert "Instrument technicals" in resp.json()["detail"]


def test_technicals_passes_the_normalised_ticker_through(monkeypatch):
    seen = []

    def fake(ticker):
        seen.append(ticker)
        payload = {"ticker": ticker, "rsi": {"value": 41.0, "zone": "neutral"}}
        return SimpleNamespace(model_dump=lambda: payload)

    monkeypatch.setattr(screener, "instrument_technicals", fake)

    resp = _client().get("/screener/technicals", params={"ticker": " adbe.n "})

    assert resp.status_code == 200
    assert seen == ["ADBE.N"]
    assert resp.json()["rsi"] == {"value": 41.0, "zone": "neutral"}


def test_technicals_rejects_a_blank_ticker(monkeypatch):
    monkeypatch.setattr(screener, "instrument_technicals", lambda t: None)

    resp = _client().get("/screener/technicals", params={"ticker": " "})

    assert resp.status_code == 400


def test_technicals_maps_value_errors_to_400(monkeypatch):
    def boom(_ticker):
        raise ValueError("ticker is required")

    monkeypatch.setattr(screener, "instrument_technicals", boom)

    resp = _client().get("/screener/technicals", params={"ticker": ".L"})

    assert resp.status_code == 400


def test_technicals_passes_return_basis_through_unchanged(monkeypatch):
    """#9370: the period returns are computed in allotmint-pro (total return,
    with ``return_basis``); this route must surface them untouched, so it has
    no return maths of its own and must not reshape or filter the payload."""
    payload = {
        "ticker": "VHYL.L",
        "returns": {"1m": 0.012, "1y": 0.081},
        "return_basis": "total",
        "rsi": {"value": 55.0, "zone": "neutral"},
    }
    monkeypatch.setattr(screener, "instrument_technicals", lambda t: SimpleNamespace(model_dump=lambda: payload))

    resp = _client().get("/screener/technicals", params={"ticker": "VHYL.L"})

    assert resp.status_code == 200
    assert resp.json() == payload
