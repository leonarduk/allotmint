from fastapi.testclient import TestClient
import pandas as pd
import pytest

from backend.app import create_app
from backend.config import config
from backend.routes import timeseries_admin


def _setup_app(monkeypatch, tmp_path, allowed_email="user@example.com"):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "google_auth_enabled", True)
    monkeypatch.setattr(config, "google_client_id", "client")
    monkeypatch.setattr(config, "allowed_emails", [allowed_email])
    app = create_app()
    return TestClient(app)


def test_google_token_flow(monkeypatch, tmp_path):
    client = _setup_app(monkeypatch, tmp_path)

    def mock_verify(token, request, audience):
        assert audience == "client"
        return {"email": "user@example.com", "email_verified": True}

    monkeypatch.setattr("backend.auth.id_token.verify_oauth2_token", mock_verify)

    # unauthenticated request
    resp = client.post("/timeseries/admin/ABC/L/refetch")
    assert resp.status_code == 401

    monkeypatch.setattr(
        timeseries_admin, "load_meta_timeseries", lambda *args, **kwargs: pd.DataFrame()
    )

    # exchange google token for JWT
    resp = client.post("/token/google", json={"token": "abc"})
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    resp = client.post("/timeseries/admin/ABC/L/refetch")
    assert resp.status_code == 200


def test_google_token_rejects_unallowed_email(monkeypatch, tmp_path):
    client = _setup_app(monkeypatch, tmp_path, allowed_email="allowed@example.com")

    def mock_verify(token, request, audience):
        return {"email": "other@example.com", "email_verified": True}

    monkeypatch.setattr("backend.auth.id_token.verify_oauth2_token", mock_verify)

    resp = client.post("/token/google", json={"token": "abc"})
    assert resp.status_code == 403


def test_missing_client_id_fails_startup(monkeypatch):
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    from backend import config as cfg
    cfg.load_config.cache_clear()
    with pytest.raises(ValueError):
        cfg.load_config()
    cfg.load_config.cache_clear()
