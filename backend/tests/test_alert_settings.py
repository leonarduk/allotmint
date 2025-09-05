from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.routes import alert_settings


def _app_for(user: str) -> TestClient:
    app = FastAPI()
    app.include_router(alert_settings.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_get_alert_threshold(monkeypatch):
    monkeypatch.setattr("backend.alerts.get_user_threshold", lambda user: 0.1)
    client = _app_for("alice")
    resp = client.get("/alert-thresholds/alice")
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.1


def test_get_alert_threshold_mismatched_owner(monkeypatch):
    monkeypatch.setattr("backend.alerts.get_user_threshold", lambda user: 0.1)
    client = _app_for("alice")
    resp = client.get("/alert-thresholds/bob")
    assert resp.status_code == 403


def test_set_alert_threshold(monkeypatch):
    called = {}

    def set_threshold(user, threshold):
        called["args"] = (user, threshold)

    monkeypatch.setattr("backend.alerts.set_user_threshold", set_threshold)
    client = _app_for("bob")
    resp = client.post("/alert-thresholds/bob", json={"threshold": 0.2})
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.2
    assert called["args"] == ("bob", 0.2)


def test_set_alert_threshold_invalid_payload(monkeypatch):
    monkeypatch.setattr(
        "backend.alerts.set_user_threshold", lambda *args, **kwargs: None
    )
    client = _app_for("alice")
    resp = client.post("/alert-thresholds/alice", json={})
    assert resp.status_code == 422
