import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.data_loader import ResolvedPaths
from backend.config import config


def _write_owner(root, owner, email):
    owner_dir = root / owner
    owner_dir.mkdir(parents=True)
    (owner_dir / "person.json").write_text(json.dumps({"owner": owner, "email": email}))
    return owner_dir


def test_approvals_authorization_enforced(tmp_path, monkeypatch):
    """With auth enabled, a user may only touch approvals for their own owner."""

    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    root = tmp_path / "accounts"
    _write_owner(root, "alice", "user@example.com")
    _write_owner(root, "alex", "other@example.com")

    app = create_app()
    app.state.accounts_root = root
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    assert client.get("/accounts/alice/approvals").status_code == 200

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
