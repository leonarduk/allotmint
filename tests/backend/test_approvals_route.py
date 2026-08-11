import json
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.common.data_loader import ResolvedPaths
from backend.config import config


def _write_owner(root, owner, email, viewers=None):
    owner_dir = root / owner
    owner_dir.mkdir(parents=True)
    payload = {"owner": owner, "email": email}
    if viewers is not None:
        payload["viewers"] = viewers
    (owner_dir / "person.json").write_text(json.dumps(payload))
    return owner_dir


def test_approvals_authorization_enforced(tmp_path, monkeypatch):
    """With auth enabled, a user may only touch approvals for their own owner."""

    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    root = tmp_path / "accounts"
    _write_owner(root, "alice", "user@example.com")
    _write_owner(root, "alex", "other@example.com")
    # ``carol`` belongs to someone else but explicitly lists our identity as a
    # viewer (the family/household path).
    _write_owner(root, "carol", "carol@example.com", viewers=["user@example.com"])

    app = create_app()
    app.state.accounts_root = root
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    # Owner match and viewer match are both authorized.
    assert client.get("/accounts/alice/approvals").status_code == 200
    assert client.get("/accounts/carol/approvals").status_code == 200

    assert client.get("/accounts/alex/approvals").status_code == 403
    forbidden_post = client.post(
        "/accounts/alex/approvals",
        json={"ticker": "PFE", "approved_on": "2024-01-01"},
    )
    assert forbidden_post.status_code == 403
    forbidden_delete = client.request("DELETE", "/accounts/alex/approvals", json={"ticker": "PFE"})
    assert forbidden_delete.status_code == 403
    # The rejected write must not have created an approvals file for ``alex``.
    assert not (root / "alex" / "approvals.json").exists()

    # A non-existent owner is rejected with 403 (not 404): authorization runs
    # before owner resolution so owner existence is not leaked.
    assert client.get("/accounts/ghost/approvals").status_code == 403


def test_demo_user_can_access_own_approvals_without_a_session(tmp_path, monkeypatch):
    """Demo mode must not reject an anonymous request for its demo owner."""

    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    root = tmp_path / "accounts"
    owner_dir = _write_owner(root, "demo", "demo@example.com")
    (owner_dir / "approvals.json").write_text(
        json.dumps({"approvals": [{"ticker": "PFE", "approved_on": "2024-01-01"}]})
    )

    app = create_app()
    app.state.accounts_root = root
    client = TestClient(app)

    response = client.get("/accounts/demo/approvals")

    assert response.status_code == 200
    assert response.json() == {"approvals": [{"ticker": "PFE", "approved_on": "2024-01-01"}]}


def test_demo_user_survives_secret_rotation_with_stale_token(tmp_path, monkeypatch):
    """A cached token from before a backend restart must not 403 in demo mode.

    ``SECRET_KEY`` is an ephemeral value regenerated on every process start
    when ``disable_auth`` is true (see ``backend/auth.py``), so any JWT issued
    by a previous run always fails signature verification on the next one.
    Before the fix this fell through to the unverified-claims path, saw a
    ``sub`` of ``user@example.com`` (the fixed stub every disable_auth login
    issues, so it belongs to no real account) not present in the allowlist,
    and raised a 403 -- causing anonymous/demo mode to appear to "expire" on
    every restart while a stale token sat in the browser (#5484).
    """

    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    root = tmp_path / "accounts"
    owner_dir = _write_owner(root, "demo", "demo@example.com")
    (owner_dir / "approvals.json").write_text(
        json.dumps({"approvals": [{"ticker": "PFE", "approved_on": "2024-01-01"}]})
    )

    app = create_app()
    app.state.accounts_root = root
    client = TestClient(app)

    stale_token = pyjwt.encode(
        {"sub": auth.DISABLE_AUTH_STUB_EMAIL, "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        "a-previous-processes-ephemeral-secret",
        algorithm="HS256",
    )
    client.headers.update({"Authorization": f"Bearer {stale_token}"})

    response = client.get("/accounts/demo/approvals")

    assert response.status_code == 200
    assert response.json() == {"approvals": [{"ticker": "PFE", "approved_on": "2024-01-01"}]}


def test_post_approval_request_falls_back_to_default_accounts_root(tmp_path, monkeypatch):
    primary_root = tmp_path / "primary"
    primary_root.mkdir()

    fallback_root = tmp_path / "fallback" / "accounts"
    owner_dir = fallback_root / "demo"
    owner_dir.mkdir(parents=True)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    virtual_root = tmp_path / "virtual"
    virtual_root.mkdir()

    def fake_resolve_paths(repo_root_arg, accounts_root_arg):
        return ResolvedPaths(repo_root=repo_root, accounts_root=fallback_root, virtual_pf_root=virtual_root)

    monkeypatch.setattr("backend.routes._accounts.data_loader.resolve_paths", fake_resolve_paths)
    monkeypatch.setattr("backend.routes.approvals.data_loader.resolve_paths", fake_resolve_paths)

    app = create_app()
    app.state.accounts_root = primary_root
    client = TestClient(app)

    resp = client.post("/accounts/demo/approval-requests", json={"ticker": "PFE"})
    assert resp.status_code == 200

    saved = owner_dir / "approval_requests.json"
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert data["requests"][0]["ticker"] == "PFE"
