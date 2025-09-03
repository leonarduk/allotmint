import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from pathlib import Path

from backend.app import create_app
from backend.config import config


@pytest.fixture
def client(monkeypatch):
    """Authenticated test client with snapshot warm disabled."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_get_instrument_admin_route(client):
    """GET returns 200 when metadata exists and 404 when missing."""
    meta_path = Path("/tmp/meta.json")
    # Existing metadata
    with patch(
        "backend.routes.instrument_admin.instrument_meta_path", return_value=meta_path
    ), patch(
        "backend.routes.instrument_admin.get_instrument_meta", return_value={"ticker": "ABC.L"}
    ):
        resp = client.get("/instrument/admin/L/ABC")
        assert resp.status_code == 200
    # Missing metadata
    with patch(
        "backend.routes.instrument_admin.instrument_meta_path", return_value=meta_path
    ), patch(
        "backend.routes.instrument_admin.get_instrument_meta", return_value={}
    ):
        resp = client.get("/instrument/admin/L/ABC")
        assert resp.status_code == 404


@pytest.mark.parametrize("exists,status", [(False, 200), (True, 409)])
def test_post_instrument_admin_route(client, exists, status):
    """POST returns 200 when creating and 409 if already exists."""
    fake_path = MagicMock()
    fake_path.exists.return_value = exists
    with patch(
        "backend.routes.instrument_admin.instrument_meta_path", return_value=fake_path
    ), patch("backend.routes.instrument_admin.save_instrument_meta"):
        resp = client.post("/instrument/admin/L/ABC", json={"ticker": "ABC.L"})
    assert resp.status_code == status


@pytest.mark.parametrize("exists,status", [(True, 200), (False, 404)])
def test_put_instrument_admin_route(client, exists, status):
    """PUT returns 200 when updating and 404 if missing."""
    fake_path = MagicMock()
    fake_path.exists.return_value = exists
    with patch(
        "backend.routes.instrument_admin.instrument_meta_path", return_value=fake_path
    ), patch("backend.routes.instrument_admin.save_instrument_meta"):
        resp = client.put("/instrument/admin/L/ABC", json={"ticker": "ABC.L"})
    assert resp.status_code == status


@pytest.mark.parametrize("exists,status", [(True, 200), (False, 404)])
def test_delete_instrument_admin_route(client, exists, status):
    """DELETE returns 200 when deleting and 404 if missing."""
    fake_path = MagicMock()
    fake_path.exists.return_value = exists
    with patch(
        "backend.routes.instrument_admin.instrument_meta_path", return_value=fake_path
    ), patch("backend.routes.instrument_admin.delete_instrument_meta"):
        resp = client.delete("/instrument/admin/L/ABC")
    assert resp.status_code == status
