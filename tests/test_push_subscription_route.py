from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config as backend_config
from backend.local_api.main import app
from backend import alerts as alert_utils
from backend.common import data_loader
from backend.common.storage import get_storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        alert_utils,
        "_SUBSCRIPTIONS_STORAGE",
        get_storage(f"file://{tmp_path / 'push.json'}"),
    )
    alert_utils._PUSH_SUBSCRIPTIONS.clear()
    original_arn = alert_utils.config.sns_topic_arn
    alert_utils.config.sns_topic_arn = None
    original_disable_auth = backend_config.config.disable_auth
    try:
        yield TestClient(app)
    finally:
        alert_utils.config.sns_topic_arn = original_arn
        backend_config.config.disable_auth = original_disable_auth


def test_push_subscription_owner_validation(client, tmp_path):
    owner = "demo"
    accounts_root = data_loader.resolve_paths(None, None).accounts_root
    assert (Path(accounts_root) / owner).exists()
    payload = {"endpoint": "https://ex", "keys": {"p256dh": "a", "auth": "b"}}

    resp = client.post(f"/alerts/push-subscription/{owner}", json=payload)
    assert resp.status_code == 200
    assert alert_utils.get_user_push_subscription(owner) == payload

    resp_bad = client.post("/alerts/push-subscription/unknown", json=payload)
    assert resp_bad.status_code == 404

    client.app.state.accounts_root = tmp_path / "does-not-exist"
    resp_del = client.delete(f"/alerts/push-subscription/{owner}")
    assert resp_del.status_code == 200
    assert alert_utils.get_user_push_subscription(owner) is None


def test_delete_unknown_owner_is_idempotent(client):
    resp = client.delete("/alerts/push-subscription/unknown")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


def test_push_subscription_falls_back_to_default_dataset(client, tmp_path):
    owner = "demo"
    payload = {"endpoint": "https://ex", "keys": {"p256dh": "a", "auth": "b"}}

    custom_root = tmp_path / "alt-root"
    custom_root.mkdir()
    client.app.state.accounts_root = custom_root

    resp = client.post(f"/alerts/push-subscription/{owner}", json=payload)
    assert resp.status_code == 200
    assert alert_utils.get_user_push_subscription(owner) == payload


def test_push_subscription_allows_demo_owner_without_auth(client):
    owner = "demo"
    payload = {"endpoint": "https://ex", "keys": {"p256dh": "pub", "auth": "secret"}}

    backend_config.config.disable_auth = False

    resp = client.post(f"/alerts/push-subscription/{owner}", json=payload)
    assert resp.status_code == 200
    assert alert_utils.get_user_push_subscription(owner) == payload
