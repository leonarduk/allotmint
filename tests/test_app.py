import os
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app import create_app


def test_health_env_variable(monkeypatch):
    monkeypatch.setenv("ALLOTMINT_ENV", "staging")
    monkeypatch.setenv("ALLOTMINT_SKIP_SNAPSHOT_WARM", "true")
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["env"] == "staging"


def test_startup_warms_snapshot(monkeypatch):
    monkeypatch.delenv("ALLOTMINT_SKIP_SNAPSHOT_WARM", raising=False)
    with patch(
        "backend.app.refresh_snapshot_in_memory_from_timeseries"
    ) as mock_refresh:
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_called_once_with(days=30)


def test_skip_snapshot_warm(monkeypatch):
    monkeypatch.setenv("ALLOTMINT_SKIP_SNAPSHOT_WARM", "true")
    with patch(
        "backend.app.refresh_snapshot_in_memory_from_timeseries"
    ) as mock_refresh:
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_not_called()
