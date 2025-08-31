from unittest.mock import patch

from fastapi.testclient import TestClient

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
    with (
        patch("backend.app.refresh_snapshot_async") as mock_refresh,
        patch("backend.app._load_snapshot", return_value=({}, None)) as mock_load,
        patch("backend.app.refresh_snapshot_in_memory") as mock_mem,
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot") as mock_update,
        patch("backend.common.instrument_api.prime_latest_prices") as mock_prime,
    ):
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_called_once_with(days=30)
    mock_load.assert_called_once_with()
    mock_mem.assert_called_once_with({}, None)
    mock_update.assert_called_once_with({})
    mock_prime.assert_called_once()


def test_skip_snapshot_warm(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    with (
        patch("backend.app.refresh_snapshot_async") as mock_refresh,
        patch("backend.app._load_snapshot") as mock_load,
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot") as mock_update,
        patch("backend.common.instrument_api.prime_latest_prices") as mock_prime,
    ):
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_not_called()
    mock_load.assert_not_called()
    mock_update.assert_not_called()
    mock_prime.assert_not_called()
