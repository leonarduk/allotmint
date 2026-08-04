import logging

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


def test_portfolio_unknown_owner_logs_owner_not_found_warning(tmp_path, caplog):
    """GET /portfolio/{owner} for an unknown owner must both 404 and emit the
    log_owner_not_found warning from its FileNotFoundError handler (#5712,
    #5690): a full request through the real app, not a call to the handler
    function directly, so the actual routing/exception-handling wiring is
    exercised end to end."""
    app = create_app()
    accounts_root = tmp_path / "accounts"
    app.state.accounts_root = accounts_root

    with caplog.at_level(logging.WARNING, logger="backend.common.errors"):
        with TestClient(app) as client:
            resp = client.get("/portfolio/ghost")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"
    assert "owner lookup: no owner found for owner=ghost" in caplog.text
