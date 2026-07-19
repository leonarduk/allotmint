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


def test_ensure_owner_access_denial_is_logged(monkeypatch, caplog):
    """A denial must be logged with enough context to diagnose the next real
    occurrence of issue #5215 (a 403 on /accounts/{owner}/approvals that
    couldn't be reproduced or root-caused from code alone) without needing
    another blind investigation. The raw identity is deliberately not logged
    (only whether one was present), since it may be a real user's email.
    """
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {})

    with caplog.at_level("WARNING", logger="backend.common.authz"):
        with pytest.raises(PermissionDeniedError):
            authz.ensure_owner_access(None, "alice")

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "alice" in message
    assert "identity_present=False" in message


def test_ensure_owner_access_denial_log_reports_identity_present_when_unauthorized(
    monkeypatch, caplog
):
    """A present-but-unauthorized identity is distinguished from no identity
    at all in the log, since they're different failure modes (wrong account
    vs. genuinely anonymous caller).
    """
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {})

    with caplog.at_level("WARNING", logger="backend.common.authz"):
        with pytest.raises(PermissionDeniedError):
            authz.ensure_owner_access("bob", "alice")

    assert "identity_present=True" in caplog.records[0].getMessage()
