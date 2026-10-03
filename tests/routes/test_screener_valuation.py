"""/screener/valuation: the allotmint-pro valuation profile plus the app's price-staleness flag.

(allotmint-pro#259.) Uses a stand-in for ``instrument_valuation`` so it runs with or without the
private package installed.
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


def _profile(ticker):
    payload = {
        "ticker": ticker,
        "nav": {
            "nav_per_share": 1.341,
            "premium_discount": -0.1611,
            "source": "reported_book_value",
        },
        "benchmark": {"ticker": "FTAL.L", "name": "FTSE All-Share", "source": "exchange_default"},
        "data_quality": {"price_stale": False, "suspect_moves": [], "warnings": []},
    }
    return SimpleNamespace(model_dump=lambda: payload)


def test_valuation_returns_402_without_the_pro_module(monkeypatch):
    monkeypatch.setattr(screener, "instrument_valuation", None)

    resp = _client().get("/screener/valuation", params={"ticker": "UKW.L"})

    assert resp.status_code == 402
    assert "Instrument valuation" in resp.json()["detail"]


def test_valuation_adds_the_price_snapshot_flag(monkeypatch):
    seen = []

    def fake(ticker):
        seen.append(ticker)
        return _profile(ticker)

    monkeypatch.setattr(screener, "instrument_valuation", fake)
    monkeypatch.setattr(
        screener.instrument_api,
        "_price_and_changes",
        lambda t: {"is_stale": True, "last_price_date": "2026-09-30"},
    )

    resp = _client().get("/screener/valuation", params={"ticker": " ukw.l "})

    assert resp.status_code == 200
    body = resp.json()
    assert seen == ["UKW.L"]
    assert body["nav"]["premium_discount"] == -0.1611
    assert body["data_quality"]["price_snapshot"] == {
        "is_stale": True,
        "last_price_date": "2026-09-30",
    }


def test_valuation_survives_a_snapshot_failure(monkeypatch):
    def boom(_ticker):
        raise RuntimeError("snapshot unavailable")

    monkeypatch.setattr(screener, "instrument_valuation", _profile)
    monkeypatch.setattr(screener.instrument_api, "_price_and_changes", boom)

    resp = _client().get("/screener/valuation", params={"ticker": "UKW.L"})

    assert resp.status_code == 200
    assert resp.json()["data_quality"]["price_snapshot"] == {
        "is_stale": None,
        "last_price_date": None,
    }


def test_valuation_rejects_a_blank_ticker(monkeypatch):
    monkeypatch.setattr(screener, "instrument_valuation", _profile)

    assert _client().get("/screener/valuation", params={"ticker": " "}).status_code == 400
    assert _client().get("/screener/valuation", params={"ticker": ".L"}).status_code == 400
