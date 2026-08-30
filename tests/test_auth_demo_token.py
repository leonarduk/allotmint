"""Tests for the demo-scoped token helpers (backend/auth.py, #7405).

These cover only the mint/verify primitives and the decode_token() hardening
that keeps a demo token from ever resolving as a normal authenticated user.
Nothing here exercises get_current_user or any route -- that wiring is out of
scope for this PR (see #7402 breakdown, steps 3+).
"""

from datetime import timedelta

import jwt
import pytest
from fastapi import FastAPI, HTTPException, Request

from backend import auth
from backend.config import config


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


def test_create_and_decode_demo_token_round_trip():
    token = auth.create_demo_access_token("demo")
    claims = auth.decode_demo_token(token)

    assert claims is not None
    assert claims.owner == "demo"
    assert claims.scope == auth.DEMO_SCOPE


def test_decode_token_rejects_demo_scoped_token():
    """Regression test for the sharpest footgun in #7402: a demo token must
    never be accepted by the existing normal-user decode path, even though
    it is signed with the same SECRET_KEY/ALGORITHM."""

    token = auth.create_demo_access_token("demo")

    assert auth.decode_token(token) is None


def test_decode_demo_token_rejects_normal_access_token():
    token = auth.create_access_token("real@example.com")

    assert auth.decode_demo_token(token) is None


def test_decode_token_still_accepts_normal_access_token():
    """No regression: a real backend JWT still decodes to its sub/email."""

    token = auth.create_access_token("real@example.com")

    assert auth.decode_token(token) == "real@example.com"


def test_decode_demo_token_rejects_expired_token():
    token = auth.create_demo_access_token("demo", expires_delta=timedelta(seconds=-1))

    assert auth.decode_demo_token(token) is None


def test_decode_token_still_raises_for_expired_normal_token():
    """decode_token()'s existing ExpiredSignatureError -> 401 behaviour for a
    normal token is unchanged by the DEMO_SCOPE guard."""

    from fastapi import HTTPException

    token = auth.create_access_token("real@example.com", expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as exc:
        auth.decode_token(token)
    assert exc.value.status_code == 401


def test_decode_demo_token_rejects_wrong_secret():
    payload = {"scope": auth.DEMO_SCOPE, "owner": "demo"}
    import datetime as dt

    payload["exp"] = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    token = jwt.encode(payload, "a-different-secret-that-is-long-enough-1234", algorithm=auth.ALGORITHM)

    assert auth.decode_demo_token(token) is None


def test_decode_demo_token_rejects_missing_owner():
    import datetime as dt

    payload = {
        "scope": auth.DEMO_SCOPE,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
    }
    token = jwt.encode(payload, auth.SECRET_KEY, algorithm=auth.ALGORITHM)

    assert auth.decode_demo_token(token) is None


def test_decode_demo_token_rejects_blank_owner():
    import datetime as dt

    payload = {
        "scope": auth.DEMO_SCOPE,
        "owner": "   ",
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
    }
    token = jwt.encode(payload, auth.SECRET_KEY, algorithm=auth.ALGORITHM)

    assert auth.decode_demo_token(token) is None


def test_create_demo_access_token_rejects_empty_owner():
    with pytest.raises(ValueError):
        auth.create_demo_access_token("")

    with pytest.raises(ValueError):
        auth.create_demo_access_token("   ")


def test_create_demo_access_token_does_not_emit_sub_claim():
    token = auth.create_demo_access_token("demo")
    payload = jwt.decode(token, options={"verify_signature": False})

    assert "sub" not in payload


def test_create_demo_access_token_honours_custom_ttl():
    token = auth.create_demo_access_token("demo", expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, options={"verify_signature": False})

    import datetime as dt

    exp = dt.datetime.fromtimestamp(payload["exp"], tz=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    assert now < exp <= now + timedelta(minutes=6)


# --- Identity resolution: get_current_user / get_active_user (#7406) -------


@pytest.mark.asyncio
async def test_get_current_user_resolves_demo_token_to_configured_owner(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    token = auth.create_demo_access_token("demo")

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        result = await auth.get_current_user(token)
        assert result == "demo"
        assert auth.is_demo_request() is True
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)


def test_get_current_user_rejects_demo_token_when_link_disabled(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", False, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    token = auth.create_demo_access_token("demo")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_current_user(token))
    assert exc.value.status_code == 401


def test_get_current_user_rejects_demo_token_owner_mismatch(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    # Token minted for a different owner than the currently configured one.
    token = auth.create_demo_access_token("someone-else")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_current_user(token))
    assert exc.value.status_code == 401


def test_demo_identity_never_admitted_by_allowed_emails(monkeypatch, tmp_path):
    """The resolved demo identity ('demo', an owner id, not an email) must
    never appear in _allowed_emails() -- that set is what admits real
    owners/viewers. Asserted directly rather than assumed, per #7406."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(config, "allowed_emails", [], raising=False)

    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()
    monkeypatch.setattr(config, "accounts_root", accounts_root)
    monkeypatch.setattr(config, "app_env", "local")

    token = auth.create_demo_access_token("demo")
    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        identity = asyncio.run(auth.get_current_user(token))
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)

    assert identity == "demo"
    assert identity not in auth._allowed_emails()
    assert identity.lower() not in auth._allowed_emails()


@pytest.mark.asyncio
async def test_get_current_user_real_token_unaffected_and_not_demo(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    token = auth.create_access_token("real@example.com")

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        result = await auth.get_current_user(token)
        assert result == "real@example.com"
        assert auth.is_demo_request() is False
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)


@pytest.mark.asyncio
async def test_demo_readonly_marker_does_not_leak_to_next_request(monkeypatch):
    """Container-reuse regression: a demo request must not leave
    is_demo_request() True for a subsequent, unrelated request in the same
    process (#7406)."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    demo_token_str = auth.create_demo_access_token("demo")
    real_token_str = auth.create_access_token("real@example.com")

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        await auth.get_current_user(demo_token_str)
        assert auth.is_demo_request() is True

        result = await auth.get_current_user(real_token_str)
        assert result == "real@example.com"
        assert auth.is_demo_request() is False
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)


@pytest.mark.asyncio
async def test_get_active_user_resolves_demo_token_to_configured_owner(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)
    token = auth.create_demo_access_token("demo")

    app = FastAPI()
    request = _make_request(app)

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        result = await auth.get_active_user(request, token=token)
        assert result == "demo"
        assert auth.is_demo_request() is True
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)


@pytest.mark.asyncio
async def test_get_active_user_rejects_demo_token_when_link_disabled(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", False, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)
    token = auth.create_demo_access_token("demo")

    app = FastAPI()
    request = _make_request(app)

    with pytest.raises(HTTPException) as exc:
        await auth.get_active_user(request, token=token)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_active_user_rejects_demo_token_owner_mismatch(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)
    token = auth.create_demo_access_token("someone-else")

    app = FastAPI()
    request = _make_request(app)

    with pytest.raises(HTTPException) as exc:
        await auth.get_active_user(request, token=token)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_active_user_real_token_unaffected_and_not_demo(monkeypatch):
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)
    token = auth.create_access_token("real@example.com")

    app = FastAPI()
    request = _make_request(app)

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        result = await auth.get_active_user(request, token=token)
        assert result == "real@example.com"
        assert auth.is_demo_request() is False
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)


@pytest.mark.asyncio
async def test_get_active_user_disable_auth_no_token_returns_local_identity(monkeypatch):
    """disable_auth=True + no token still returns the local login identity
    exactly as today -- the demo path must not interfere (#7406)."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "_resolve_identity_when_auth_disabled", lambda token: "local@example.com")

    app = FastAPI()
    request = _make_request(app)

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        result = await auth.get_active_user(request, token=None)
        assert result == "local@example.com"
        assert auth.is_demo_request() is False
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)


@pytest.mark.asyncio
async def test_get_current_user_disable_auth_no_token_returns_local_identity(monkeypatch):
    """Same regression guard as above, for get_current_user (#7406)."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "_resolve_identity_when_auth_disabled", lambda token: "local@example.com")

    current_token = auth.current_user.set(None)
    demo_token = auth.demo_readonly.set(False)
    try:
        result = await auth.get_current_user(token=None)
        assert result == "local@example.com"
        assert auth.is_demo_request() is False
    finally:
        auth.current_user.reset(current_token)
        auth.demo_readonly.reset(demo_token)
