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
