import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.alerts as alerts
from backend.auth import get_current_user
from backend.routes.alert_settings import router


def _client_for(user: str) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_get_threshold_success(monkeypatch):
    called = {}

    def fake_get(user: str):
        called["user"] = user
        return 0.25

    monkeypatch.setattr(alerts, "get_user_threshold", fake_get)
    client = _client_for("alice")
    resp = client.get("/alert-thresholds/alice")
    assert resp.status_code == 200
    assert resp.json() == {"threshold": 0.25}
    assert called["user"] == "alice"


def test_get_threshold_owner_mismatch(monkeypatch):
    monkeypatch.setattr(alerts, "get_user_threshold", lambda u: 0.2)
    client = _client_for("alice")
    resp = client.get("/alert-thresholds/bob")
    assert resp.status_code == 403


def test_get_threshold_error(monkeypatch):
    def boom(user: str):
        raise RuntimeError("fail")

    monkeypatch.setattr(alerts, "get_user_threshold", boom)
    client = _client_for("bob")
    resp = client.get("/alert-thresholds/bob")
    assert resp.status_code == 500


def test_set_threshold_success(monkeypatch):
    called = {}

    def fake_set(user: str, threshold: float):
        called["user"] = user
        called["threshold"] = threshold

    monkeypatch.setattr(alerts, "set_user_threshold", fake_set)
    client = _client_for("charlie")
    payload = {"threshold": 0.1}
    resp = client.post("/alert-thresholds/charlie", json=payload)
    assert resp.status_code == 200
    assert resp.json() == payload
    assert called == {"user": "charlie", "threshold": 0.1}


def test_set_threshold_error(monkeypatch):
    def boom(user: str, threshold: float):
        raise RuntimeError("fail")

    monkeypatch.setattr(alerts, "set_user_threshold", boom)
    client = _client_for("delta")
    resp = client.post("/alert-thresholds/delta", json={"threshold": 0.5})
    assert resp.status_code == 500
