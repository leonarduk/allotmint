import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi import HTTPException, Request

from backend import auth


def _future_exp():
    return datetime.now(timezone.utc) + timedelta(minutes=15)


def test_create_and_decode_token():
    token = auth.create_access_token("user@example.com")
    assert auth.decode_token(token) == "user@example.com"


def test_decode_token_expired():
    token = auth.create_access_token("user@example.com", expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as exc:
        auth.decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException):
        asyncio.run(auth.get_current_user("bad"))


def test_get_current_user_valid():
    token = auth.create_access_token("alice@example.com")
    assert asyncio.run(auth.get_current_user(token)) == "alice@example.com"


def test_get_current_user_local_override(monkeypatch):
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth.config, "local_login_email", "local@example.com", raising=False)
    assert asyncio.run(auth.get_current_user(None)) == "local@example.com"


def test_resolve_identity_when_auth_disabled_stale_stub_token_falls_back(monkeypatch):
    """A signature-invalid token carrying the disable_auth stub email is
    treated as a stale self-issued token (secret rotated on restart), not a
    foreign caller -- it falls back to the local login identity instead of a
    403 (#5484)."""

    monkeypatch.setattr(auth.config, "local_login_email", "local@example.com", raising=False)
    stale_token = pyjwt.encode(
        {"sub": auth.DISABLE_AUTH_STUB_EMAIL, "exp": _future_exp()},
        "a-different-secret-from-this-processes-SECRET_KEY",
        algorithm="HS256",
    )
    assert auth._resolve_identity_when_auth_disabled(stale_token) == "local@example.com"


def test_resolve_identity_when_auth_disabled_rejects_unrecognized_email(monkeypatch):
    """A signature-invalid token for a real, unprovisioned email is still
    rejected -- only the disable_auth stub email gets the stale-token
    fallback."""

    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"alice@example.com"})
    foreign_token = pyjwt.encode(
        {"sub": "someone-else@example.com", "exp": _future_exp()},
        "a-different-secret-from-this-processes-SECRET_KEY",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        auth._resolve_identity_when_auth_disabled(foreign_token)
    assert exc.value.status_code == 403


def test_verify_google_token_success(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", "client")

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        return {"email": "a@b.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"a@b.com"})
    assert auth.verify_google_token("token") == "a@b.com"


def test_verify_google_token_unverified(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", "client")

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        return {"email": "a@b.com", "email_verified": False}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_verify_google_token_unauthorized(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", "client")

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        return {"email": "c@d.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"a@b.com"})
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 403


def test_verify_google_token_no_allowed(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", "client")

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        return {"email": "a@b.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: set())
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 403


def test_verify_google_token_missing_email(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", "client")

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        return {"email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_verify_google_token_invalid_token(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", "client")

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        raise ValueError("bad token")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_verify_google_token_missing_client_id(monkeypatch):
    monkeypatch.setattr(auth.config, "google_client_id", None)

    def fake_verify(*args, **kwargs):  # should not be called
        raise AssertionError("verify_oauth2_token should not be called")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 400


def test_allowed_emails_local(monkeypatch, tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()
    (accounts_root / "alice").mkdir()
    monkeypatch.setattr(
        auth,
        "resolve_paths",
        lambda repo_root, accounts_root_param: SimpleNamespace(
            repo_root=tmp_path, accounts_root=accounts_root, virtual_pf_root=None
        ),
    )
    monkeypatch.setattr(
        auth,
        "config",
        SimpleNamespace(app_env="local", repo_root=tmp_path, accounts_root=Path("accounts")),
    )
    monkeypatch.setattr(
        auth,
        "load_person_metadata",
        lambda owner, data_root=None: type("Meta", (), {"email": f"{owner}@example.com"})(),
    )
    emails = auth._allowed_emails()
    assert "alice@example.com" in emails


def test_get_active_user_returns_local_override(monkeypatch):
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth.config, "local_login_email", "helper@example.com", raising=False)

    result = asyncio.run(auth.get_active_user(Request(scope={"type": "http"})))
    assert result == "helper@example.com"


def test_missing_jwt_secret_raises_error(monkeypatch):
    import importlib

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth.config, "disable_auth", False)
    with pytest.raises(RuntimeError):
        importlib.reload(auth)
    monkeypatch.setenv("JWT_SECRET", "a-restored-test-secret-that-is-at-least-32-bytes")
    importlib.reload(auth)
