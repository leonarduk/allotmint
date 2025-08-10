from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app import create_app
from backend.config import config


def test_health_env_variable(monkeypatch):
    monkeypatch.setattr(config, "app_env", "staging")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["env"] == "staging"


def test_startup_warms_snapshot(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch(
        "backend.app.refresh_snapshot_in_memory_from_timeseries"
    ) as mock_refresh:
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_called_once_with(days=30)


def test_skip_snapshot_warm(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    with patch(
        "backend.app.refresh_snapshot_in_memory_from_timeseries"
    ) as mock_refresh:
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_not_called()
