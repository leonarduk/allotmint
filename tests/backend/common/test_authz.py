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


def test_ensure_owner_access_no_log_when_disable_auth(monkeypatch, caplog):
    """The disable_auth early return must precede the denial log (#5431)."""

    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {})

    with caplog.at_level("WARNING", logger="backend.common.authz"):
        authz.ensure_owner_access(None, "alice")

    assert caplog.records == []


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


def test_ensure_owner_access_denial_log_reports_identity_present_when_unauthorized(monkeypatch, caplog):
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


# ---------------------------------------------------------------------------
# Demo-scoped owner access (#7408)
# ---------------------------------------------------------------------------


def _fail_load_person_meta(owner, root=None):
    """A demo request must never consult person.json metadata (#7408)."""

    raise AssertionError("demo-scoped ensure_owner_access must not load person metadata")


def test_ensure_owner_access_demo_request_allows_configured_owner(monkeypatch):
    monkeypatch.setattr(authz, "is_demo_request", lambda: True)
    monkeypatch.setattr(config, "demo_link_owner", "demo")
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", _fail_load_person_meta)

    authz.ensure_owner_access("demo", "demo")


def test_ensure_owner_access_demo_request_denies_other_owner(monkeypatch):
    monkeypatch.setattr(authz, "is_demo_request", lambda: True)
    monkeypatch.setattr(config, "demo_link_owner", "demo")
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", _fail_load_person_meta)

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access("demo", "alice")


def test_ensure_owner_access_demo_request_denied_even_with_disable_auth_true(monkeypatch):
    """The deployed Lambda runs with disable_auth=True; the demo case must
    not inherit that no-op (#7408)."""

    monkeypatch.setattr(authz, "is_demo_request", lambda: True)
    monkeypatch.setattr(config, "demo_link_owner", "demo")
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(authz, "load_person_meta", _fail_load_person_meta)

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access("demo", "alice")


def test_ensure_owner_access_demo_request_not_widened_by_viewers(monkeypatch):
    """A viewers entry equal to the demo owner id on some other owner's
    person.json must not widen demo access -- the demo decision comes from
    config alone (#7408)."""

    monkeypatch.setattr(authz, "is_demo_request", lambda: True)
    monkeypatch.setattr(config, "demo_link_owner", "demo")
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", _fail_load_person_meta)

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access("demo", "alice")


def test_ensure_owner_access_demo_request_denied_when_owner_not_configured(monkeypatch):
    """A demo request is denied for every owner when demo_link_owner is unset
    (fail closed rather than matching a blank/None owner)."""

    monkeypatch.setattr(authz, "is_demo_request", lambda: True)
    monkeypatch.setattr(config, "demo_link_owner", None)
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", _fail_load_person_meta)

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access("demo", "demo")


def test_ensure_owner_access_demo_request_owner_match_case_insensitive(monkeypatch):
    monkeypatch.setattr(authz, "is_demo_request", lambda: True)
    monkeypatch.setattr(config, "demo_link_owner", "Demo")
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", _fail_load_person_meta)

    authz.ensure_owner_access("demo", "  DEMO  ")


def test_ensure_owner_access_non_demo_request_unaffected(monkeypatch):
    """Normal (non-demo) requests are unaffected by the demo branch."""

    monkeypatch.setattr(authz, "is_demo_request", lambda: False)
    monkeypatch.setattr(config, "demo_link_owner", "demo")
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: {"email": "alice@example.com"})

    authz.ensure_owner_access("alice@example.com", "alice")

    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access("bob", "alice")
