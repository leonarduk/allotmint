import asyncio
import importlib
import logging
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from importlib import machinery, util

import backend.auth as auth
import backend.common.data_loader as dl
from tests.conftest import _real_verify_google_token
import tests.conftest as tests_conftest


async def _empty_receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(app: FastAPI) -> Request:
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "GET",
        "path": "/",
        "query_string": b"",
    }
    return Request(scope, _empty_receive)


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


def test_allowed_emails_local_relative_root(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    accounts = repo_root / "accounts"
    accounts.mkdir(parents=True)
    (accounts / "alice").mkdir()
    (accounts / "carol").mkdir()
    (accounts / "notes.txt").write_text("ignore")

    monkeypatch.setattr(auth.config, "app_env", "local", raising=False)
    monkeypatch.setattr(auth.config, "accounts_root", "accounts", raising=False)
    monkeypatch.setattr(auth.config, "repo_root", repo_root, raising=False)

    monkeypatch.setattr(
        auth,
        "resolve_paths",
        lambda repo_root, _: SimpleNamespace(repo_root=repo_root, accounts_root=repo_root / "default"),
    )
    monkeypatch.setattr(
        auth,
        "load_person_meta",
        lambda owner, data_root=None: {"email": f"{owner}@example.com"},
    )

    emails = auth._allowed_emails()

    assert emails == {"alice@example.com", "carol@example.com"}


def test_allowed_emails_local_fallback_handles_errors(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    fallback_root = tmp_path / "resolved"
    (fallback_root / "alice").mkdir(parents=True)
    (fallback_root / "bob").mkdir()

    monkeypatch.setattr(auth.config, "app_env", "local", raising=False)
    monkeypatch.setattr(auth.config, "accounts_root", None, raising=False)
    monkeypatch.setattr(auth.config, "repo_root", repo_root, raising=False)

    monkeypatch.setattr(
        auth,
        "resolve_paths",
        lambda repo_root, _: SimpleNamespace(accounts_root=fallback_root, repo_root=repo_root),
    )

    def fake_load(owner, data_root=None):
        if owner == "bob":
            raise RuntimeError("failed")
        return {"email": f"{owner}@Example.com"}

    monkeypatch.setattr(auth, "load_person_meta", fake_load)

    emails = auth._allowed_emails()

    assert emails == {"alice@example.com"}


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


def test_user_from_token_missing_token_raises_http_exception():
    with pytest.raises(HTTPException) as exc:
        auth._user_from_token(token=None)

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


def test_verify_google_token_rejects_unknown_email(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        return {"email": "intruder@example.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"user@example.com"})

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")

    assert exc.value.status_code == 403


def test_verify_google_token_verification_failure(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        raise ValueError("bad token")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")
    assert exc.value.status_code == 401


def test_verify_google_token_missing_email(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        return {"email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("token")

    assert exc.value.status_code == 401
    assert "Email missing" in exc.value.detail


def test_verify_google_token_no_allowed_emails(monkeypatch, caplog):
    monkeypatch.setattr(auth, "verify_google_token", _real_verify_google_token)
    monkeypatch.setattr(auth.config, "google_client_id", "client", raising=False)

    def fake_verify(token, request, client_id):
        return {"email": "user@example.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: set())

    with caplog.at_level("ERROR", logger=auth.logger.name):
        with pytest.raises(HTTPException) as exc:
            auth.verify_google_token("token")

    assert exc.value.status_code == 403
    assert any("No allowed emails" in record.getMessage() for record in caplog.records)


def test_get_current_user_valid_token():
    token = auth.create_access_token("alice@example.com")
    assert asyncio.run(auth.get_current_user(token)) == "alice@example.com"


def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException):
        asyncio.run(auth.get_current_user("bad"))


@pytest.mark.asyncio
async def test_get_active_user_auth_enabled(monkeypatch):
    app = FastAPI()
    request = _make_request(app)

    token = auth.create_access_token("active@example.com")

    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)

    captured: dict[str, str | None] = {}

    def fake_user_from_token(raw_token: str | None) -> str:
        captured["token"] = raw_token
        return "active@example.com"

    token_var = auth.current_user.set(None)
    try:
        monkeypatch.setattr(auth, "_user_from_token", fake_user_from_token)
        result = await auth.get_active_user(request, token=token)
    finally:
        auth.current_user.reset(token_var)

    assert result == "active@example.com"
    assert captured == {"token": token}


@pytest.mark.asyncio
async def test_get_current_user_returns_local_identity_when_disabled(monkeypatch):
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "local_login_identity", lambda: "local@example.com")

    def fail_user_from_token(token: str | None) -> str:  # pragma: no cover - safety guard
        raise AssertionError("_user_from_token should not be called when no token is provided")

    monkeypatch.setattr(auth, "_user_from_token", fail_user_from_token)

    assert await auth.get_current_user(token=None) == "local@example.com"


@pytest.mark.asyncio
async def test_get_current_user_disabled_without_identity(monkeypatch):
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "local_login_identity", lambda: None)

    captured: dict[str, str | None] = {}

    def fake_user_from_token(token: str | None) -> str:
        captured["token"] = token
        raise HTTPException(status_code=401, detail="invalid")

    monkeypatch.setattr(auth, "_user_from_token", fake_user_from_token)

    with pytest.raises(HTTPException):
        await auth.get_current_user(token=None)

    assert captured == {"token": None}


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


def test_missing_secret_key_in_production_raises(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(auth.config, "app_env", "production", raising=False)

    loader = machinery.SourceFileLoader("backend.auth_temp", auth.__file__)
    spec = util.spec_from_loader(loader.name, loader)
    module = util.module_from_spec(spec)

    with pytest.raises(RuntimeError):
        loader.exec_module(module)

    sys.modules.pop("backend.auth_temp", None)


def test_authenticate_user_delegates_to_verification(monkeypatch):
    sentinel = object()

    def fake_verify(token: str) -> object:
        assert token == "stub"
        return sentinel

    monkeypatch.setattr(auth, "verify_google_token", fake_verify)

    assert auth.authenticate_user("stub") is sentinel
