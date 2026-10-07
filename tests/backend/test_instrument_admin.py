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

    def fake_save_instrument_meta(ticker: str, exchange: str, payload: dict, **_kwargs: Any) -> None:
        saved["args"] = (ticker, exchange)
        saved["payload"] = payload

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_instrument_meta_path)
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

    def fake_fetch(ticker: str, exchange: str) -> dict[str, Any]:
        assert ticker == "ABC"
        assert exchange == "NYSE"
        return {"name": "Alpha Corp", "currency": "GBP", "instrument_type": "EQUITY"}

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_instrument_meta_path)
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", fake_get_instrument_meta)
    monkeypatch.setattr(
        instrument_admin,
        "_fetch_metadata_from_yahoo",
        fake_fetch,
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

    def fake_fetch(ticker: str, exchange: str) -> dict[str, Any]:
        assert ticker == "ABC"
        assert exchange == "NYSE"
        return {"name": "Alpha Corp", "currency": "GBP", "instrument_type": "EQUITY"}

    def fake_save(ticker: str, exchange: str, payload: dict[str, Any], **_kwargs: Any) -> None:
        stored["args"] = (ticker, exchange)
        stored["payload"] = payload

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_instrument_meta_path)
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


def _morningstar_client(monkeypatch, meta: dict, resolved: str | None) -> tuple[TestClient, dict]:
    app = FastAPI()
    app.include_router(instrument_admin.router)
    state: dict[str, Any] = {"lookups": []}

    def fake_resolve(isin: str, exchange: str, currency: str | None) -> str | None:
        state["lookups"].append((isin, exchange, currency))
        return resolved

    def fake_save(ticker: str, exchange: str, payload: dict, **_kwargs: Any) -> None:
        state["saved"] = payload

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", lambda *_a: _DummyPath())
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", lambda _t: dict(meta))
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    monkeypatch.setattr(instrument_admin.morningstar, "resolve_sec_id", fake_resolve)
    monkeypatch.setattr(instrument_admin.config, "offline_mode", False)
    return TestClient(app), state


def test_morningstar_id_resolves_and_saves(monkeypatch):
    meta = {"ticker": "PHGP.L", "exchange": "L", "isin": "JE00B1VS3770", "currency": "GBX"}
    client, state = _morningstar_client(monkeypatch, meta, "0P0000AATZ")
    with client:
        resp = client.post("/instrument/admin/L/PHGP/morningstar-id")
    assert resp.json() == {"status": "resolved", "morningstar_id": "0P0000AATZ"}
    assert state["lookups"] == [("JE00B1VS3770", "L", "GBX")]
    assert state["saved"]["morningstar_id"] == "0P0000AATZ"
    assert state["saved"]["isin"] == "JE00B1VS3770"


def test_morningstar_id_returns_saved_id_without_lookup(monkeypatch):
    meta = {"ticker": "PHGP.L", "exchange": "L", "isin": "JE00B1VS3770", "morningstar_id": "0P0000AATZ"}
    client, state = _morningstar_client(monkeypatch, meta, "0P0SHOULDNT")
    with client:
        resp = client.post("/instrument/admin/L/PHGP/morningstar-id")
    assert resp.json() == {"status": "saved", "morningstar_id": "0P0000AATZ"}
    assert state["lookups"] == []
    assert "saved" not in state


def test_morningstar_id_unresolved_without_isin_or_match(monkeypatch):
    client, state = _morningstar_client(monkeypatch, {"ticker": "ABC.L", "exchange": "L"}, "0P0SHOULDNT")
    with client:
        resp = client.post("/instrument/admin/L/ABC/morningstar-id")
    assert resp.json() == {"status": "unresolved", "morningstar_id": None}
    assert state["lookups"] == []

    meta = {"ticker": "ABC.L", "exchange": "L", "isin": "GB00BH4HKS39"}
    client, state = _morningstar_client(monkeypatch, meta, None)
    with client:
        resp = client.post("/instrument/admin/L/ABC/morningstar-id")
    assert resp.json() == {"status": "unresolved", "morningstar_id": None}
    assert "saved" not in state
