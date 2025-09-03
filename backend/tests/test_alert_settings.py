from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import alert_settings


def test_get_alert_threshold(monkeypatch):
    app = FastAPI()
    app.include_router(alert_settings.router)

    monkeypatch.setattr("backend.alerts.get_user_threshold", lambda user: 0.1)

    with TestClient(app) as client:
        resp = client.get("/alert-thresholds/alice")
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.1


def test_set_alert_threshold(monkeypatch):
    app = FastAPI()
    app.include_router(alert_settings.router)

    called = {}

    def set_threshold(user, threshold):
        called["args"] = (user, threshold)

    monkeypatch.setattr("backend.alerts.set_user_threshold", set_threshold)

    with TestClient(app) as client:
        resp = client.post("/alert-thresholds/bob", json={"threshold": 0.2})
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.2
    assert called["args"] == ("bob", 0.2)


def test_set_alert_threshold_invalid_payload(monkeypatch):
    app = FastAPI()
    app.include_router(alert_settings.router)

    monkeypatch.setattr("backend.alerts.set_user_threshold", lambda *args, **kwargs: None)

    with TestClient(app) as client:
        resp = client.post("/alert-thresholds/alice", json={})
    assert resp.status_code == 422
