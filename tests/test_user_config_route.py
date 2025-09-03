import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, ANY

from backend.app import create_app
import backend.routes.user_config as routes
from backend.common.user_config import UserConfig


def test_get_user_config_success(monkeypatch):
    cfg = UserConfig(hold_days_min=5, max_trades_per_month=10,
                     approval_exempt_types=["foo"],
                     approval_exempt_tickers=["ABC"])
    load_mock = Mock(return_value=cfg)
    save_mock = Mock()
    monkeypatch.setattr(routes, "load_user_config", load_mock)
    monkeypatch.setattr(routes, "save_user_config", save_mock)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/user-config/alice")
    assert resp.status_code == 200
    assert resp.json() == cfg.to_dict()
    load_mock.assert_called_once_with("alice", ANY)
    save_mock.assert_not_called()


def test_get_user_config_not_found(monkeypatch):
    load_mock = Mock(side_effect=FileNotFoundError)
    save_mock = Mock()
    monkeypatch.setattr(routes, "load_user_config", load_mock)
    monkeypatch.setattr(routes, "save_user_config", save_mock)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/user-config/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"
    load_mock.assert_called_once_with("missing", ANY)
    save_mock.assert_not_called()


def test_update_user_config_success(monkeypatch):
    data = {"hold_days_min": 7}
    cfg = UserConfig(hold_days_min=7)

    load_mock = Mock(return_value=cfg)
    save_mock = Mock()
    monkeypatch.setattr(routes, "load_user_config", load_mock)
    monkeypatch.setattr(routes, "save_user_config", save_mock)

    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/user-config/alice", json=data)
    assert resp.status_code == 200
    assert resp.json() == cfg.to_dict()
    save_mock.assert_called_once_with("alice", data, ANY)
    load_mock.assert_called_once_with("alice", ANY)


def test_update_user_config_not_found(monkeypatch):
    data = {"hold_days_min": 7}
    save_mock = Mock(side_effect=FileNotFoundError)
    load_mock = Mock()
    monkeypatch.setattr(routes, "load_user_config", load_mock)
    monkeypatch.setattr(routes, "save_user_config", save_mock)

    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/user-config/missing", json=data)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"
    save_mock.assert_called_once_with("missing", data, ANY)
    load_mock.assert_not_called()
