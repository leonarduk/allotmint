import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.user_config import UserConfig
from backend.config import config


def _auth_client():
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    return _auth_client()


@pytest.fixture
def mock_user_config(monkeypatch):
    store = {"alice": {"hold_days_min": 5}}

    def fake_load(owner: str, accounts_root=None):
        if owner not in store:
            raise FileNotFoundError(owner)
        return UserConfig.from_dict(store[owner])

    def fake_save(owner: str, cfg, accounts_root=None):
        if owner not in store:
            raise FileNotFoundError(owner)
        data = cfg if isinstance(cfg, dict) else cfg.to_dict()
        store[owner].update(data)

    monkeypatch.setattr("backend.common.user_config.load_user_config", fake_load)
    monkeypatch.setattr("backend.common.user_config.save_user_config", fake_save)
    monkeypatch.setattr("backend.routes.user_config.load_user_config", fake_load)
    monkeypatch.setattr("backend.routes.user_config.save_user_config", fake_save)
    return store


def test_fetch_and_update_user_config(client, mock_user_config):
    resp = client.get("/user-config/alice")
    assert resp.status_code == 200
    assert resp.json() == {
        "hold_days_min": 5,
        "max_trades_per_month": None,
        "approval_exempt_types": None,
        "approval_exempt_tickers": None,
    }

    resp = client.post("/user-config/alice", json={"max_trades_per_month": 7})
    assert resp.status_code == 200
    data = resp.json()
    assert data["hold_days_min"] == 5
    assert data["max_trades_per_month"] == 7
    assert mock_user_config["alice"]["max_trades_per_month"] == 7


def test_missing_owner_returns_error(client, mock_user_config):
    resp = client.get("/user-config/bob")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"

    resp = client.post("/user-config/bob", json={"hold_days_min": 1})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


def test_defaults_from_config_return_lists(client):
    resp = client.get("/user-config/alex")
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_exempt_types"] == ["ETF"]
    assert data["approval_exempt_tickers"] == []
