"""Tests for the demo-scoped token helpers (backend/auth.py, #7405).

These cover only the mint/verify primitives and the decode_token() hardening
that keeps a demo token from ever resolving as a normal authenticated user.
Nothing here exercises get_current_user or any route -- that wiring is out of
scope for this PR (see #7402 breakdown, steps 3+).
"""

from datetime import timedelta

import jwt
import pytest

from backend import auth


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
