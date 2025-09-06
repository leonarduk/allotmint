import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import auth


def test_create_and_decode_token():
    token = auth.create_access_token("user@example.com")
    assert auth.decode_token(token) == "user@example.com"


def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException):
        asyncio.run(auth.get_current_user("bad"))


def test_get_current_user_valid():
    token = auth.create_access_token("alice@example.com")
    assert asyncio.run(auth.get_current_user(token)) == "alice@example.com"


def test_verify_google_token_success(monkeypatch):
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda token, request, client_id: {"email": "a@b.com", "email_verified": True},
    )
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"a@b.com"})
    assert auth.verify_google_token("token") == "a@b.com"


def test_verify_google_token_unverified(monkeypatch):
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda token, request, client_id: {"email": "a@b.com", "email_verified": False},
    )
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_verify_google_token_unauthorized(monkeypatch):
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda token, request, client_id: {"email": "c@d.com", "email_verified": True},
    )
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"a@b.com"})
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 403


def test_verify_google_token_no_allowed(monkeypatch):
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda token, request, client_id: {"email": "a@b.com", "email_verified": True},
    )
    monkeypatch.setattr(auth, "_allowed_emails", lambda: set())
    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 403


def test_allowed_emails_local(monkeypatch, tmp_path):
    monkeypatch.setattr(
        auth,
        "resolve_paths",
        lambda repo_root, accounts_root: SimpleNamespace(accounts_root=tmp_path),
    )
    monkeypatch.setattr(
        auth,
        "config",
        SimpleNamespace(app_env="local", repo_root=tmp_path, accounts_root=tmp_path),
    )
    (tmp_path / "alice").mkdir()
    monkeypatch.setattr(auth, "load_person_meta", lambda owner, data_root=None: {"email": f"{owner}@example.com"})
    emails = auth._allowed_emails()
    assert "alice@example.com" in emails
