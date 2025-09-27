from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.instrument_admin as instrument_admin


class _DummyPath:
    def __init__(self, exists: bool = True) -> None:
        self._exists = exists

    def exists(self) -> bool:
        return self._exists


def test_update_instrument_preserves_existing_fields(monkeypatch):
    app = FastAPI()
    app.include_router(instrument_admin.router)

    existing_meta = {
        "ticker": "ABC.NYSE",
        "exchange": "NYSE",
        "instrumentType": "Equity",
        "name": "Alpha",
        "asset_class": "Stocks",
    }
    saved: dict[str, dict] = {}

    def fake_instrument_meta_path(ticker: str, exchange: str) -> _DummyPath:
        assert ticker == "ABC"
        assert exchange == "NYSE"
        return _DummyPath()

    def fake_get_instrument_meta(full_ticker: str) -> dict:
        assert full_ticker == "ABC.NYSE"
        return dict(existing_meta)

    def fake_save_instrument_meta(ticker: str, exchange: str, payload: dict) -> None:
        saved["args"] = (ticker, exchange)
        saved["payload"] = payload

    monkeypatch.setattr(
        instrument_admin, "instrument_meta_path", fake_instrument_meta_path
    )
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", fake_get_instrument_meta)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save_instrument_meta)

    with TestClient(app) as client:
        resp = client.put(
            "/instrument/admin/NYSE/ABC",
            json={"name": "Alpha Corp"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "updated"}

    assert saved["args"] == ("ABC", "NYSE")
    payload = saved["payload"]
    assert payload["name"] == "Alpha Corp"
    assert payload["instrumentType"] == "Equity"
    assert payload["asset_class"] == "Stocks"
    assert payload["ticker"] == "ABC.NYSE"
    assert payload["exchange"] == "NYSE"


def test_refresh_instrument_preview(monkeypatch):
    app = FastAPI()
    app.include_router(instrument_admin.router)

    saved: dict[str, Any] = {}

    def fake_instrument_meta_path(ticker: str, exchange: str) -> _DummyPath:
        assert ticker == "ABC"
        assert exchange == "NYSE"
        return _DummyPath()

    def fake_get_instrument_meta(full_ticker: str) -> dict[str, Any]:
        assert full_ticker == "ABC.NYSE"
        return {
            "ticker": "ABC.NYSE",
            "exchange": "NYSE",
            "name": "Alpha",  # existing value should be preserved until confirmed
            "currency": "USD",
        }

    def fake_fetch(full_ticker: str) -> dict[str, Any]:
        assert full_ticker == "ABC.NYSE"
        return {"name": "Alpha Corp", "currency": "GBP", "instrument_type": "EQUITY"}

    monkeypatch.setattr(
        instrument_admin, "instrument_meta_path", fake_instrument_meta_path
    )
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", fake_get_instrument_meta)
    monkeypatch.setattr(
        instrument_admin, "_fetch_metadata_from_yahoo", fake_fetch,
    )
    monkeypatch.setattr(
        instrument_admin,
        "save_instrument_meta",
        lambda ticker, exchange, payload: saved.setdefault("called", True),
    )

    with TestClient(app) as client:
        resp = client.post("/instrument/admin/NYSE/ABC/refresh")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "preview"
    assert data["metadata"]["name"] == "Alpha Corp"
    assert data["metadata"]["currency"] == "GBP"
    assert data["metadata"]["instrumentType"] == "EQUITY"
    assert data["changes"] == {
        "name": {"from": "Alpha", "to": "Alpha Corp"},
        "currency": {"from": "USD", "to": "GBP"},
        "instrument_type": {"from": None, "to": "EQUITY"},
    }
    assert "called" not in saved


def test_refresh_instrument_confirm(monkeypatch):
    app = FastAPI()
    app.include_router(instrument_admin.router)

    stored: dict[str, Any] = {}

    def fake_instrument_meta_path(ticker: str, exchange: str) -> _DummyPath:
        return _DummyPath()

    def fake_get_instrument_meta(full_ticker: str) -> dict[str, Any]:
        return {"ticker": full_ticker, "exchange": "NYSE", "name": "Alpha", "currency": "USD"}

    def fake_fetch(full_ticker: str) -> dict[str, Any]:
        return {"name": "Alpha Corp", "currency": "GBP", "instrument_type": "EQUITY"}

    def fake_save(ticker: str, exchange: str, payload: dict[str, Any]) -> None:
        stored["args"] = (ticker, exchange)
        stored["payload"] = payload

    monkeypatch.setattr(
        instrument_admin, "instrument_meta_path", fake_instrument_meta_path
    )
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", fake_get_instrument_meta)
    monkeypatch.setattr(instrument_admin, "_fetch_metadata_from_yahoo", fake_fetch)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)

    with TestClient(app) as client:
        resp = client.post(
            "/instrument/admin/NYSE/ABC/refresh",
            json={"preview": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert stored["args"] == ("ABC", "NYSE")
    payload = stored["payload"]
    assert payload["name"] == "Alpha Corp"
    assert payload["currency"] == "GBP"
    assert payload["instrument_type"] == "EQUITY"
    assert payload["instrumentType"] == "EQUITY"
    assert payload["ticker"] == "ABC.NYSE"
    assert payload["exchange"] == "NYSE"
