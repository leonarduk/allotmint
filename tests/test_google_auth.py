from typing import Optional
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import ConfigValidationError, reload_config
from backend.routes import timeseries_admin
from backend import auth


def _setup_app(monkeypatch, tmp_path, allowed_email: Optional[str] = "user@example.com"):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))

    app = create_app()

    cfg_module = sys.modules["backend.config"]
    monkeypatch.setattr(cfg_module.config, "skip_snapshot_warm", True)
    monkeypatch.setattr(cfg_module.config, "disable_auth", False)
    monkeypatch.setattr(cfg_module.config, "google_auth_enabled", True)
    monkeypatch.setattr(cfg_module.config, "google_client_id", "client")

    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir(parents=True)
    if allowed_email:
        owner_dir = accounts_root / "owner"
        owner_dir.mkdir(parents=True)
        (owner_dir / "person.json").write_text(
            f'{{"email": "{allowed_email}"}}', encoding="utf-8"
        )
    monkeypatch.setattr(cfg_module.config, "accounts_root", accounts_root)

    return TestClient(app)


def test_google_token_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "verify_google_token", lambda token: "user@example.com")
    client = _setup_app(monkeypatch, tmp_path)
    monkeypatch.setattr(
        timeseries_admin, "load_meta_timeseries", lambda *args, **kwargs: pd.DataFrame()
    )
    resp = client.post("/token/google", json={"token": "abc"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    resp = client.post("/timeseries/admin/ABC/L/refetch")
    assert resp.status_code == 200


def test_google_token_rejects_unallowed_email(monkeypatch, tmp_path):
    from fastapi import HTTPException

    def fake(token):
        raise HTTPException(status_code=403, detail="Unauthorized email")

    monkeypatch.setattr(auth, "verify_google_token", fake)
    client = _setup_app(monkeypatch, tmp_path)
    resp = client.post("/token/google", json={"token": "abc"})
    assert resp.status_code == 403


def test_google_token_rejects_when_no_accounts(monkeypatch, tmp_path):
    from fastapi import HTTPException

    def fake(token):
        raise HTTPException(status_code=403, detail="Unauthorized email")

    monkeypatch.setattr(auth, "verify_google_token", fake)
    client = _setup_app(monkeypatch, tmp_path, allowed_email=None)
    resp = client.post("/token/google", json={"token": "abc"})
    assert resp.status_code == 403


def test_startup_requires_google_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    with pytest.raises(ConfigValidationError):
        reload_config()


def test_missing_client_id_fails_startup(monkeypatch):
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    with pytest.raises(ConfigValidationError):
        reload_config()
