import pytest
from fastapi import HTTPException

from backend import auth
from backend.config import config

ORIGINAL_VERIFY = auth.verify_google_token


def test_create_and_decode_token_round_trip():
    token = auth.create_access_token("user@example.com")
    assert auth.decode_token(token) == "user@example.com"


def test_decode_token_invalid_returns_none():
    assert auth.decode_token("not-a-token") is None


def test_verify_google_token_rejects_when_no_allowed_emails(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "verify_google_token", ORIGINAL_VERIFY)
    root = tmp_path / "accounts"
    root.mkdir()
    monkeypatch.setattr(config, "accounts_root", root)
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "google_client_id", "client")

    def fake_verify(token, request, audience):
        return {"email": "user@example.com", "email_verified": True}

    monkeypatch.setattr("backend.auth.id_token.verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("dummy")
    assert exc.value.status_code == 403


def test_verify_google_token_rejects_unverified_email(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "verify_google_token", ORIGINAL_VERIFY)
    root = tmp_path / "accounts"
    root.mkdir()
    monkeypatch.setattr(config, "accounts_root", root)
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "google_client_id", "client")

    def fake_verify(token, request, audience):
        return {"email": "user@example.com", "email_verified": False}

    monkeypatch.setattr("backend.auth.id_token.verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("dummy")
    assert exc.value.status_code == 401
