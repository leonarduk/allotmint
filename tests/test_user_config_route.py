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
    store = {
        "alice": {"hold_days_min": 5},
        "alex": {},
    }

    def fake_load(owner: str, accounts_root=None):
        if owner not in store:
            raise FileNotFoundError(owner)
        data = store[owner]
        if not data:
            return UserConfig(
                hold_days_min=config.hold_days_min,
                max_trades_per_month=config.max_trades_per_month,
                approval_exempt_types=config.approval_exempt_types,
                approval_exempt_tickers=config.approval_exempt_tickers,
            )
        return UserConfig.from_dict(data)

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


def test_defaults_from_config_return_lists(client, mock_user_config):
    resp = client.get("/user-config/alex")
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_exempt_types"] == ["ETF"]
    assert data["approval_exempt_tickers"] == []


def _auth_enabled_client(monkeypatch):
    """Build a client with authentication (and thus owner scoping) enabled.

    ``disable_auth`` is an override attribute preserved across ``create_app``'s
    config reload, so setting it before app creation makes both the router-level
    auth dependency and the per-owner authorization check active.
    """

    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    return _auth_client()


def test_owner_config_authorization_enforced(monkeypatch, mock_user_config):
    """A logged-in user may only read/write owners they are authorized for."""

    # ``user@example.com`` (the identity behind the "good" token) is mapped to
    # owner ``alice`` only; ``alex`` belongs to someone else.
    def fake_meta(owner, root=None):
        return {"email": "user@example.com"} if owner == "alice" else {}

    monkeypatch.setattr("backend.common.authz.load_person_meta", fake_meta)
    client = _auth_enabled_client(monkeypatch)

    assert client.get("/user-config/alice").status_code == 200

    forbidden_get = client.get("/user-config/alex")
    assert forbidden_get.status_code == 403

    forbidden_post = client.post("/user-config/alex", json={"hold_days_min": 1})
    assert forbidden_post.status_code == 403
    # The unauthorized write must not have mutated the other owner's config.
    assert "hold_days_min" not in mock_user_config["alex"]
