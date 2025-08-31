from fastapi.testclient import TestClient
import pandas as pd

from backend.app import create_app
from backend.config import config
from backend.routes import timeseries_admin


def test_timeseries_admin_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(config, "disable_auth", False)
    app = create_app()
    client = TestClient(app)

    # Unauthenticated request should be rejected
    resp = client.post("/timeseries/admin/ABC/L/refetch")
    assert resp.status_code == 401

    # Mock timeseries fetch to avoid external IO
    monkeypatch.setattr(
        timeseries_admin, "load_meta_timeseries", lambda *args, **kwargs: pd.DataFrame()
    )

    # Acquire auth token and retry
    token = client.post(
        "/token", data={"username": "testuser", "password": "password"}
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    resp = client.post("/timeseries/admin/ABC/L/refetch")
    assert resp.status_code == 200
