from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def test_health_env_variable(monkeypatch):
    monkeypatch.setattr(config, "app_env", "staging")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch("backend.bootstrap.startup.refresh_snapshot_async") as mock_refresh:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
    mock_refresh.assert_called_once_with(days=30)
    assert resp.status_code == 200
    assert resp.json()["env"] == "staging"


def test_startup_warms_snapshot(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with (
        patch("backend.bootstrap.startup.refresh_snapshot_async") as mock_refresh,
        patch("backend.bootstrap.startup._load_snapshot", return_value=({}, None)) as mock_load,
        patch("backend.bootstrap.startup.refresh_snapshot_in_memory") as mock_mem,
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
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with (
        patch("backend.bootstrap.startup.refresh_snapshot_async") as mock_refresh,
        patch("backend.bootstrap.startup._load_snapshot") as mock_load,
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot") as mock_update,
        patch("backend.common.instrument_api.prime_latest_prices") as mock_prime,
    ):
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_called_once_with(days=30)
    mock_load.assert_not_called()
    mock_update.assert_not_called()
    mock_prime.assert_not_called()


def test_create_app_registers_rebalance_route(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    app = create_app()

    registered_paths = {route.path for route in app.routes}
    assert "/rebalance" in registered_paths


def test_docs_endpoint_returns_200(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch("backend.bootstrap.startup.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/docs")
    assert resp.status_code == 200


def test_docs_returns_200_when_prime_latest_prices_fails(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)

    def _fail():
        raise RuntimeError("simulated network failure on cold start")

    with (
        patch("backend.bootstrap.startup.refresh_snapshot_async"),
        patch("backend.bootstrap.startup._load_snapshot", return_value=({}, None)),
        patch("backend.bootstrap.startup.refresh_snapshot_in_memory"),
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot"),
        patch("backend.common.instrument_api.prime_latest_prices", side_effect=_fail),
    ):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/docs")
    assert resp.status_code == 200


def test_docs_returns_200_when_update_latest_prices_fails(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)

    def _fail(_snapshot):
        raise RuntimeError("simulated update_latest_prices failure")

    with (
        patch("backend.bootstrap.startup.refresh_snapshot_async"),
        patch("backend.bootstrap.startup._load_snapshot", return_value=({}, None)),
        patch("backend.bootstrap.startup.refresh_snapshot_in_memory"),
        patch(
            "backend.common.instrument_api.update_latest_prices_from_snapshot",
            side_effect=_fail,
        ),
        patch("backend.common.instrument_api.prime_latest_prices"),
    ):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/docs")
    assert resp.status_code == 200
