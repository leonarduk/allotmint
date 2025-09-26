from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import get_active_user
from backend.config import load_config, config
from backend.routes import alert_settings


def _app_for(user: str) -> TestClient:
    app = FastAPI()
    app.include_router(alert_settings.router)
    app.dependency_overrides[get_active_user] = lambda: user
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


def test_alert_thresholds_auth_disabled(monkeypatch):
    monkeypatch.setattr("backend.alerts.get_user_threshold", lambda user: 0.3)

    recorded: dict[str, tuple[str, float]] = {}

    def set_threshold(user, threshold):
        recorded["args"] = (user, threshold)

    monkeypatch.setattr("backend.alerts.set_user_threshold", set_threshold)

    # Ensure configuration reflects auth being disabled.
    load_config.cache_clear()
    monkeypatch.setattr(config, "disable_auth", True, raising=False)

    app = FastAPI()
    app.include_router(alert_settings.router)
    client = TestClient(app)

    resp = client.get("/alert-thresholds/demo")
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.3

    resp = client.post("/alert-thresholds/demo", json={"threshold": 0.5})
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.5
    assert recorded["args"] == ("demo", 0.5)
