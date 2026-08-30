import asyncio
import importlib
import logging
import sys
from datetime import datetime, timedelta, timezone
from importlib import machinery, util
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

import backend.auth as auth
import backend.common.data_loader as dl
import tests.conftest as tests_conftest
from backend.common.account_models import PersonMetadata
from tests.conftest import _real_verify_google_token


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
        "load_person_metadata",
        lambda owner, data_root=None: PersonMetadata(email=f"{owner}@example.com"),
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
    monkeypatch.setattr(auth.config, "allowed_emails", None, raising=False)
    monkeypatch.setattr(auth.config, "accounts_root", "accounts", raising=False)
    monkeypatch.setattr(auth.config, "repo_root", repo_root, raising=False)

    monkeypatch.setattr(
        auth,
        "resolve_paths",
        lambda repo_root, _: SimpleNamespace(repo_root=repo_root, accounts_root=repo_root / "default"),
    )
    monkeypatch.setattr(
        auth,
        "load_person_metadata",
        lambda owner, data_root=None: PersonMetadata(email=f"{owner}@example.com"),
    )

    emails = auth._allowed_emails()

    assert emails == {"alice@example.com", "carol@example.com"}


def test_allowed_emails_local_fallback_handles_errors(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    fallback_root = tmp_path / "resolved"
    (fallback_root / "alice").mkdir(parents=True)
    (fallback_root / "bob").mkdir()

    monkeypatch.setattr(auth.config, "app_env", "local", raising=False)
    monkeypatch.setattr(auth.config, "allowed_emails", None, raising=False)
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
        return PersonMetadata(email=f"{owner}@Example.com")

    monkeypatch.setattr(auth, "load_person_metadata", fake_load)

    emails = auth._allowed_emails()

    assert emails == {"alice@example.com"}


def test_allowed_emails_aws_s3_error(monkeypatch, caplog):
    monkeypatch.setattr(auth.config, "app_env", "aws", raising=False)
    monkeypatch.setattr(auth.config, "allowed_emails", None, raising=False)
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
    assert any("Failed to list allowed emails from S3" in record.message for record in caplog.records)


def test_allowed_emails_bootstrap_allowlist_survives_s3_error(monkeypatch, caplog):
    """The configured bootstrap owner must still get in even if S3 fails (#6130).

    A transient S3 error must not lock out the deployment's configured owner
    email(s) -- only the S3-provisioned portion of the set is lost.
    """

    monkeypatch.setattr(auth.config, "app_env", "aws", raising=False)
    monkeypatch.setattr(auth.config, "allowed_emails", ["Owner@Example.com"], raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    class FakeS3:
        def list_objects_v2(self, **kwargs):  # noqa: ARG002 - kwargs for API parity
            raise auth.BotoCoreError()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda name: FakeS3()))

    with caplog.at_level("ERROR"):
        emails = auth._allowed_emails()

    assert emails == {"owner@example.com"}


def test_allowed_emails_bootstrap_allowlist_when_no_accounts_provisioned(monkeypatch):
    """A fresh AWS deployment with zero S3 accounts must still admit the configured owner (#6130)."""

    monkeypatch.setattr(auth.config, "app_env", "aws", raising=False)
    monkeypatch.setattr(auth.config, "allowed_emails", ["owner@example.com"], raising=False)
    monkeypatch.delenv(dl.DATA_BUCKET_ENV, raising=False)

    assert auth._allowed_emails() == {"owner@example.com"}


def test_configured_allowed_emails_normalizes_list(monkeypatch):
    """``config.allowed_emails`` (already a ``list[str]``, however sourced --
    config.lambda.yaml's yaml list or the ALLOWED_EMAILS env var, both parsed
    by ``_parse_str_list`` in backend/config.py) must become a lower-cased,
    whitespace-trimmed set, not be iterated character-by-character (#6130).

    Deliberately does not exercise ``reload_config()``: config.py's parsing of
    ALLOWED_EMAILS into a list is already covered by
    tests/test_config.py::test_allowed_emails_env_override, and re-entering
    ``reload_config()`` here would trip its unrelated "preserve a
    monkeypatched allowed_emails across reload" bookkeeping (backend/config.py
    ``_allowed_emails_overridden``) whenever an earlier test in this file has
    already monkeypatched ``config.allowed_emails`` directly -- this test's
    job is only ``_configured_allowed_emails()``'s own aggregation logic.
    """

    monkeypatch.setattr(
        auth.config,
        "allowed_emails",
        [" Owner@Example.com", "Second@Example.com ", "", "   "],
        raising=False,
    )
    assert auth._configured_allowed_emails() == {"owner@example.com", "second@example.com"}


def test_configured_allowed_emails_empty_when_unset(monkeypatch):
    monkeypatch.setattr(auth.config, "allowed_emails", None, raising=False)
    assert auth._configured_allowed_emails() == set()


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
async def test_get_current_user_returns_token_user_when_decode_succeeds(monkeypatch):
    """When disable_auth=True and decode_token decodes the token (HS256 app JWT),
    get_current_user returns the token user without falling back to local identity."""

    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "decode_token", lambda _token: "tokenuser@example.com")

    def fail_local_identity() -> str:  # pragma: no cover - safety guard
        raise AssertionError("local_login_identity should not be called when decode_token succeeds")

    monkeypatch.setattr(auth, "local_login_identity", fail_local_identity)

    assert await auth.get_current_user(token="app-hs256-stub") == "tokenuser@example.com"


@pytest.mark.asyncio
async def test_get_current_user_reads_email_claim_when_token_not_app_jwt(monkeypatch):
    """When disable_auth=True and decode_token returns None (e.g. a Cognito RS256
    token whose signature API Gateway's authorizer already validated),
    get_current_user resolves the caller's own email from the token's claims
    rather than collapsing every caller into the shared local identity (#4750)."""

    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "decode_token", lambda _token: None)
    monkeypatch.setattr(auth, "local_login_identity", lambda: "local@example.com")
    monkeypatch.setattr(auth, "_unverified_claims", lambda _token: {"email": "steve@example.com"})
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"steve@example.com"})

    assert await auth.get_current_user(token="cognito-rs256-stub") == "steve@example.com"


@pytest.mark.asyncio
async def test_get_current_user_rejects_unrecognized_email_claim(monkeypatch):
    """An unprovisioned email must be rejected, not mapped to the local/demo identity."""

    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "decode_token", lambda _token: None)
    monkeypatch.setattr(auth, "local_login_identity", lambda: "local@example.com")
    monkeypatch.setattr(auth, "_unverified_claims", lambda _token: {"email": "unknown@example.com"})
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"steve@example.com"})

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(token="cognito-rs256-stub")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_disabled_without_identity(monkeypatch):
    """When disable_auth=True, token=None, and local_login_identity() returns None,
    get_current_user has no identity to fall back to and no token to decode. It must
    reject the request directly rather than falling through to _user_from_token,
    which is reserved for the auth-enabled path (#4795)."""

    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "local_login_identity", lambda: None)
    auth.current_user.set("stale@example.com")

    def fail_user_from_token(token: str | None) -> str:  # pragma: no cover - safety guard
        raise AssertionError("_user_from_token should not be called on the disable_auth path")

    monkeypatch.setattr(auth, "_user_from_token", fail_user_from_token)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(token=None)

    assert exc_info.value.status_code == 401
    assert auth.current_user.get() is None
    # The message must be actionable (points to the Support page fix) rather
    # than a bare/generic 401, since this is the out-of-the-box state of a
    # fresh local checkout (#6058).
    assert "Support" in exc_info.value.detail
    assert "Local login override" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_enabled_without_token(monkeypatch):
    """When disable_auth=False (the default) and token=None, get_current_user must
    fall straight through to _user_from_token(None) and reject the request.
    local_login_identity() is the disable_auth-only fallback (see
    _resolve_identity_when_auth_disabled) and must never be consulted on the
    auth-enabled path."""

    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)

    def fail_local_login_identity() -> str | None:  # pragma: no cover - safety guard
        raise AssertionError("local_login_identity should not be called on the auth-enabled path")

    monkeypatch.setattr(auth, "local_login_identity", fail_local_login_identity)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(token=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid authentication credentials"


def test_missing_secret_key_generates_ephemeral_secret(monkeypatch, caplog):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("TESTING", "")
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)

    caplog.set_level(logging.WARNING, logger=auth.logger.name)

    reloaded = importlib.reload(auth)

    assert reloaded.SECRET_KEY
    assert any(
        "JWT_SECRET not set; using ephemeral secret for development" in record.getMessage() for record in caplog.records
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


def test_verify_cognito_token_success(monkeypatch):
    class FakeSigningKey:
        key = "public-key"

    class FakeJwksClient:
        def __init__(self, url):
            assert url == ("https://cognito-idp.eu-west-2.amazonaws.com/pool/.well-known/jwks.json")

        def get_signing_key_from_jwt(self, token):
            assert token == "token"
            return FakeSigningKey()

    def fake_decode(token, *args, **kwargs):
        if kwargs.get("options") == {"verify_signature": False}:
            return {"iss": "https://cognito-idp.eu-west-2.amazonaws.com/pool"}
        assert kwargs["audience"] == "client"
        assert kwargs["issuer"] == "https://cognito-idp.eu-west-2.amazonaws.com/pool"
        return {
            "aud": "client",
            "email": "user@example.com",
            "email_verified": True,
            "iss": kwargs["issuer"],
            "token_use": "id",
        }

    monkeypatch.setattr(auth, "_jwks_clients", {})
    monkeypatch.setattr(auth.jwt, "PyJWKClient", FakeJwksClient)
    monkeypatch.setattr(auth.jwt, "decode", fake_decode)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"user@example.com"})

    assert auth.verify_cognito_token("token", "client") == "user@example.com"


def test_get_jwks_client_caches_by_issuer(monkeypatch):
    created: list[object] = []

    class FakeClient:
        pass

    def fake_constructor(url: str) -> FakeClient:  # noqa: ARG001
        client = FakeClient()
        created.append(client)
        return client

    local_cache: dict[str, object] = {}
    monkeypatch.setattr(auth, "_jwks_clients", local_cache)
    # Patch the constructor reference used inside _get_jwks_client.
    monkeypatch.setattr(auth.jwt, "PyJWKClient", fake_constructor, raising=False)

    issuer = "https://cognito-idp.eu-west-2.amazonaws.com/pool"
    first = auth._get_jwks_client(issuer)
    second = auth._get_jwks_client(issuer)

    assert first is second
    assert len(created) == 1


def test_verify_cognito_token_rejects_cognito_prefixed_non_aws_issuer(monkeypatch):
    def fake_decode(token, *args, **kwargs):
        return {"iss": "https://cognito-idp.attacker.com/pool"}

    monkeypatch.setattr(auth.jwt, "decode", fake_decode)

    with pytest.raises(HTTPException) as exc:
        auth.verify_cognito_token("token", "client")

    assert exc.value.status_code == 401


def test_verify_cognito_token_rejects_unsupported_issuer(monkeypatch):
    def fake_decode(token, *args, **kwargs):
        return {"iss": "https://issuer.example.com/pool"}

    monkeypatch.setattr(auth.jwt, "decode", fake_decode)

    with pytest.raises(HTTPException) as exc:
        auth.verify_cognito_token("token", "client")

    assert exc.value.status_code == 401


def test_is_cognito_id_token_accepts_valid_token_without_checking_allowed_emails(monkeypatch):
    """is_cognito_id_token must not call _authorize_email/_allowed_emails --
    unlike verify_cognito_token, it only checks structural token validity
    (#7522). Failing _allowed_emails on purpose here proves it is never
    reached."""

    class FakeSigningKey:
        key = "public-key"

    class FakeJwksClient:
        def __init__(self, url):
            assert url == "https://cognito-idp.eu-west-2.amazonaws.com/pool/.well-known/jwks.json"

        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    def fake_decode(token, *args, **kwargs):
        if kwargs.get("options") == {"verify_signature": False}:
            return {"iss": "https://cognito-idp.eu-west-2.amazonaws.com/pool"}
        assert kwargs["audience"] == "client"
        return {
            "aud": "client",
            "email": "user@example.com",
            "email_verified": False,
            "iss": kwargs["issuer"],
            "token_use": "id",
        }

    def _fail_allowed_emails():
        raise AssertionError("is_cognito_id_token must not consult _allowed_emails()")

    monkeypatch.setattr(auth, "_jwks_clients", {})
    monkeypatch.setattr(auth.jwt, "PyJWKClient", FakeJwksClient)
    monkeypatch.setattr(auth.jwt, "decode", fake_decode)
    monkeypatch.setattr(auth, "_allowed_emails", _fail_allowed_emails)

    assert auth.is_cognito_id_token("token", ["client"]) is True


def test_is_cognito_id_token_tries_each_candidate_client_id(monkeypatch):
    """A token whose aud matches the second candidate (e.g. the smoke-test
    client) must still be admitted."""

    def fake_verify_claims(token, client_id):
        if client_id != "smoke-client":
            raise HTTPException(status_code=401, detail="Invalid Cognito token")
        return {"aud": client_id}

    monkeypatch.setattr(auth, "_verify_cognito_claims", fake_verify_claims)

    assert auth.is_cognito_id_token("token", ["ui-client", "smoke-client"]) is True


def test_is_cognito_id_token_skips_blank_client_ids(monkeypatch):
    calls: list[str] = []

    def fake_verify_claims(token, client_id):
        calls.append(client_id)
        raise HTTPException(status_code=401, detail="Invalid Cognito token")

    monkeypatch.setattr(auth, "_verify_cognito_claims", fake_verify_claims)

    assert auth.is_cognito_id_token("token", ["", "ui-client", ""]) is False
    assert calls == ["ui-client"]


def test_is_cognito_id_token_rejects_when_no_candidate_matches(monkeypatch):
    def fake_verify_claims(token, client_id):
        raise HTTPException(status_code=401, detail="Invalid Cognito token")

    monkeypatch.setattr(auth, "_verify_cognito_claims", fake_verify_claims)

    assert auth.is_cognito_id_token("token", ["ui-client"]) is False
