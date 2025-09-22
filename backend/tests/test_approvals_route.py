import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.data_loader import ResolvedPaths


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

    resp = client.post("/accounts/demo/approval-requests", json={"ticker": "AAPL"})
    assert resp.status_code == 200

    saved = owner_dir / "approval_requests.json"
    assert saved.exists()
    data = json.loads(saved.read_text())
    assert data["requests"][0]["ticker"] == "AAPL"
