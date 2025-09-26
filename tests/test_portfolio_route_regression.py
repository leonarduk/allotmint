from fastapi.testclient import TestClient

from backend.app import create_app


def test_portfolio_unknown_owner_does_not_create_directory(tmp_path):
    app = create_app()
    accounts_root = tmp_path / "accounts"
    missing_owner = accounts_root / "ghost"
    app.state.accounts_root = accounts_root

    with TestClient(app) as client:
        resp = client.get("/portfolio/ghost")
        assert resp.status_code == 404

    assert not missing_owner.exists()
