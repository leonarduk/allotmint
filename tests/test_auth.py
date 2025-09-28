import asyncio
import importlib
import logging
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.auth as auth
import backend.common.data_loader as dl
from tests.conftest import _real_verify_google_token
import tests.conftest as tests_conftest


def test_allowed_emails_local_filesystem(monkeypatch, tmp_path):
    accounts_root = tmp_path / "accounts"
    (accounts_root / "alice").mkdir(parents=True)
    (accounts_root / "bob").mkdir()
    monkeypatch.setattr(
        auth,
        "config",
        SimpleNamespace(app_env="local", repo_root=tmp_path, accounts_root=str(accounts_root)),
    )
    monkeypatch.setattr(
        auth,
        "load_person_meta",
        lambda owner, data_root=None: {"email": f"{owner}@example.com"},
    )
    emails = auth._allowed_emails()
    assert emails == {"alice@example.com", "bob@example.com"}


def test_allowed_emails_aws_s3_error(monkeypatch, caplog):
    monkeypatch.setattr(auth.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    class FakeS3:
        def list_objects_v2(self, **kwargs):  # noqa: ARG002 - kwargs for API parity
            raise auth.BotoCoreError()

    def fake_client(name):
        assert name == "s3"
        return FakeS3()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level("ERROR"):
        emails = auth._allowed_emails()

    assert emails == set()
    assert any(
        "Failed to list allowed emails from S3" in record.message for record in caplog.records
    )


def test_create_and_decode_token_round_trip():
    token = auth.create_access_token("user@example.com")
    assert auth.decode_token(token) == "user@example.com"


def test_decode_token_invalid_returns_none():
    assert auth.decode_token("invalid") is None


def test_decode_token_expired_raises_http_exception():
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = auth.jwt.encode(
        {"sub": "user@example.com", "exp": expired},
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        auth.decode_token(token)

    assert exc.value.status_code == 401


def test_verify_google_token_success(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        assert client_id == "client"
        return {"email": "user@example.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"user@example.com"})

    assert auth.verify_google_token("token") == "user@example.com"


def test_verify_google_token_missing_client_id(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", None, raising=False)

    def fake_verify(*args, **kwargs):  # noqa: ARG002
        raise AssertionError("verify_oauth2_token should not be called")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 400


def test_verify_google_token_unverified_email(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        return {"email": "user@example.com", "email_verified": False}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_verify_google_token_verification_failure(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        raise ValueError("bad token")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_get_current_user_valid_token():
    token = auth.create_access_token("alice@example.com")
    assert asyncio.run(auth.get_current_user(token)) == "alice@example.com"


def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException):
        asyncio.run(auth.get_current_user("bad"))


def test_missing_secret_key_generates_ephemeral_secret(monkeypatch, caplog):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("TESTING", "")
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)

    caplog.set_level(logging.WARNING, logger=auth.logger.name)

    reloaded = importlib.reload(auth)

    assert reloaded.SECRET_KEY
    assert any(
        "JWT_SECRET not set; using ephemeral secret for development" in record.getMessage()
        for record in caplog.records
    )

    tests_conftest._real_verify_google_token = reloaded.verify_google_token
