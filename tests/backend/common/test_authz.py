"""Unit tests for per-owner authorization helpers."""

import pytest

from backend.common import authz
from backend.common.errors import PermissionDeniedError
from backend.config import config


@pytest.mark.parametrize(
    "identity,owner,meta,expected",
    [
        # Identity equals the owner id (case-insensitive).
        ("alice", "alice", {}, True),
        ("ALICE", "alice", {}, True),
        ("  alice  ", "alice", {}, True),
        # Identity matches the owner's configured email.
        ("alice@example.com", "alice", {"email": "alice@example.com"}, True),
        ("ALICE@EXAMPLE.COM", "alice", {"email": "alice@example.com"}, True),
        # Identity appears in the viewers list (family/household model).
        ("mum@example.com", "alice", {"viewers": ["mum@example.com"]}, True),
        # Unrelated identity is rejected even when metadata is populated.
        (
            "bob",
            "alice",
            {"email": "alice@example.com", "viewers": ["mum@example.com"]},
            False,
        ),
        ("bob", "alice", {}, False),
        # Missing / blank identities are never authorized.
        (None, "alice", {}, False),
        ("", "alice", {}, False),
        ("   ", "alice", {}, False),
        # Malformed metadata degrades safely.
        ("bob", "alice", {"viewers": "not-a-list"}, False),
    ],
)
def test_identity_can_access_owner(identity, owner, meta, expected):
    assert authz.identity_can_access_owner(identity, owner, meta) is expected


def test_ensure_owner_access_noop_when_auth_disabled(monkeypatch):
    """Local/demo mode must not enforce owner scoping or read metadata."""

    monkeypatch.setattr(config, "disable_auth", True)
    calls = {"count": 0}

    def fake_meta(owner, root=None):
        calls["count"] += 1
        return {}

    monkeypatch.setattr(authz, "load_person_meta", fake_meta)

    authz.ensure_owner_access("bob", "alice")
    assert calls["count"] == 0


def test_ensure_owner_access_allows_authorized(monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {"email": "alice@example.com"})

    authz.ensure_owner_access("alice@example.com", "alice")


def test_ensure_owner_access_rejects_unauthorized(monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {})

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access("bob", "alice")


def test_ensure_owner_access_rejects_missing_identity(monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {})

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access(None, "alice")
