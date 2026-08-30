"""Integration tests for POST /demo-link (#7409): the admin-gated endpoint that
mints a demo-scoped token.

Covers the two independent gates (admin + ``config.demo_link_enabled``), the
missing-owner refusal, that a minted token's claims match configuration and
decode via ``decode_demo_token``, that the token is rate-limited and never
logged, and a lightweight end-to-end sanity check that a freshly minted token
is still write-blocked (#7407) and owner-scoped (#7408) exactly as those
PRs' own tests already prove.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.bootstrap import load_runtime_config as _real_load_runtime_config
from backend.config import config

DEMO_BLOCKED_DETAIL = "Demo access is read-only"
OWNER_FORBIDDEN_DETAIL = "Not authorized for this owner"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _demo_link_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    admin_emails: str = "admin@example.com",
    disable_auth: bool = False,
    demo_link_enabled: bool = True,
    demo_link_owner: str | None = "demo",
    demo_link_ttl_hours: int = 72,
    demo_link_mint_rate_limit: str | None = None,
):
    """Build an app wired for POST /demo-link tests.

    ``create_app()`` builds its own ``cfg`` via
    ``backend.bootstrap.load_runtime_config()`` (a *new* ``Config`` reloaded
    from env/yaml, not the shared ``backend.config.config`` singleton --
    only the fixed attribute set in ``backend.bootstrap.config._OVERRIDE_ATTRS``
    carries over from the singleton). ``demo_link_*`` is not in that set, so
    monkeypatching the singleton alone (as ``tests/test_auth_demo_token.py``
    does for the auth-module-level tests) would not reach the ``cfg`` this
    endpoint actually reads. Instead, ``load_runtime_config`` itself is
    monkeypatched here to load the real config and then apply the
    ``demo_link_*`` overrides this test wants, leaving everything else
    (accounts_root, disable_auth via the singleton override path, etc.)
    exactly as the real bootstrap would produce it.
    """
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    monkeypatch.setenv("ADMIN_EMAILS", admin_emails)

    def _patched_load_runtime_config():
        cfg = _real_load_runtime_config()
        cfg.demo_link_enabled = demo_link_enabled
        cfg.demo_link_owner = demo_link_owner
        cfg.demo_link_ttl_hours = demo_link_ttl_hours
        if demo_link_mint_rate_limit is not None:
            cfg.demo_link_mint_rate_limit = demo_link_mint_rate_limit
        return cfg

    monkeypatch.setattr("backend.app.load_runtime_config", _patched_load_runtime_config)

    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        return create_app()


# --- Admin gate --------------------------------------------------------------


def test_demo_link_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _demo_link_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "other@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code == 403
    assert "token" not in resp.json()


def test_demo_link_anonymous_caller_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """No token/override at all: the admin gate must still deny, not fall
    through to a mint. With ``disable_auth=False`` and no bearer token,
    ``get_active_user`` itself rejects with 401 (missing credentials) before
    ``require_admin``'s own allowlist check would ever run -- either way the
    request is refused and no token is minted."""
    app = _demo_link_app(monkeypatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code in (401, 403)
    assert "token" not in resp.json()


def test_demo_link_local_dev_admin_bypass_still_requires_demo_link_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """require_admin's local-dev quirk (no ADMIN_EMAILS + disable_auth=True
    lets current_user be None) must NOT be enough on its own to mint a demo
    link -- the demo_link_enabled gate below is what closes that hole."""
    app = _demo_link_app(
        monkeypatch,
        admin_emails="",
        disable_auth=True,
        demo_link_enabled=False,
    )
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code == 404
    assert "token" not in resp.json()


# --- demo_link_enabled gate ---------------------------------------------------


def test_demo_link_refused_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _demo_link_app(monkeypatch, demo_link_enabled=False)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code == 404
    assert "token" not in resp.json()


# --- Missing owner -------------------------------------------------------------


@pytest.mark.parametrize("owner", [None, "", "   "])
def test_demo_link_refused_when_owner_unconfigured(monkeypatch: pytest.MonkeyPatch, owner) -> None:
    app = _demo_link_app(monkeypatch, demo_link_owner=owner)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code == 503
    assert "token" not in resp.json()


# --- Happy path ----------------------------------------------------------------


def test_demo_link_mints_token_for_admin_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _demo_link_app(monkeypatch, demo_link_owner="demo", demo_link_ttl_hours=6)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "demo"
    assert isinstance(body["token"], str) and body["token"]

    claims = auth.decode_demo_token(body["token"])
    assert claims is not None
    assert claims.owner == "demo"
    assert claims.scope == auth.DEMO_SCOPE

    expires_at = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    assert now < expires_at <= now + timedelta(hours=6, minutes=1)


def test_demo_link_admin_allowlist_enforced_over_owner_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Case-insensitive admin matching, like /api-console's own test suite."""
    app = _demo_link_app(monkeypatch, admin_emails="Admin@Example.COM")
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/demo-link")

    assert resp.status_code == 200


# --- Rate limiting ---------------------------------------------------------------


def test_demo_link_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _demo_link_app(monkeypatch, demo_link_mint_rate_limit="1/minute")
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        first = client.post("/demo-link")
        second = client.post("/demo-link")

    assert first.status_code == 200
    assert second.status_code == 429


# --- Never logged ------------------------------------------------------------------


def test_demo_link_token_is_never_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    app = _demo_link_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with caplog.at_level(logging.DEBUG):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/demo-link")

    assert resp.status_code == 200
    token = resp.json()["token"]
    assert token
    for record in caplog.records:
        assert token not in record.getMessage()


# --- End-to-end: the minted token is still write-blocked and owner-scoped ------


def test_minted_token_is_still_write_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A demo token minted via this endpoint, replayed against a mutating
    endpoint, is still rejected by #7407's global write gate."""
    app = _demo_link_app(monkeypatch, demo_link_owner="demo")
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        mint_resp = client.post("/demo-link")
        assert mint_resp.status_code == 200
        token = mint_resp.json()["token"]

        del app.dependency_overrides[auth.get_current_user]
        write_resp = client.post("/transactions", json={}, headers=_bearer(token))

    assert write_resp.status_code == 403
    assert write_resp.json()["detail"] == DEMO_BLOCKED_DETAIL


def test_minted_token_is_still_owner_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A demo token minted via this endpoint, replayed against a different
    owner's data, is still denied by #7408's owner-scoping gate."""
    app = _demo_link_app(monkeypatch, demo_link_owner="demo")
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        mint_resp = client.post("/demo-link")
        assert mint_resp.status_code == 200
        token = mint_resp.json()["token"]

        del app.dependency_overrides[auth.get_current_user]
        other_owner_resp = client.get("/user-config/some-other-owner", headers=_bearer(token))

    assert other_owner_resp.status_code == 403
    assert other_owner_resp.json()["detail"] == OWNER_FORBIDDEN_DETAIL
