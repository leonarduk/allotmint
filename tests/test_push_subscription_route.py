import pytest
from fastapi.testclient import TestClient

from backend.local_api.main import app
from backend import alerts as alert_utils
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
    try:
        yield TestClient(app)
    finally:
        alert_utils.config.sns_topic_arn = original_arn


def test_push_subscription_owner_validation(client):
    owners = client.get("/owners").json()
    assert any(o["owner"] == "demo" for o in owners)
    owner = "demo"
    payload = {"endpoint": "https://ex", "keys": {"p256dh": "a", "auth": "b"}}

    resp = client.post(f"/alerts/push-subscription/{owner}", json=payload)
    assert resp.status_code == 200
    assert alert_utils.get_user_push_subscription(owner) == payload

    resp_bad = client.post("/alerts/push-subscription/unknown", json=payload)
    assert resp_bad.status_code == 404

    resp_del = client.delete(f"/alerts/push-subscription/{owner}")
    assert resp_del.status_code == 200
    assert alert_utils.get_user_push_subscription(owner) is None
