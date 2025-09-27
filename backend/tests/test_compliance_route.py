from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import compliance


def test_validate_demo_owner_available_with_testing(monkeypatch, tmp_path):
    clone_root = tmp_path / "clone" / "accounts"
    (clone_root / "demo").mkdir(parents=True)
    (clone_root / "alice").mkdir(parents=True)
    (clone_root / "alice" / "portfolio.json").write_text("{}")
    (clone_root / "demo" / "portfolio.json").write_text("{}")

    monkeypatch.setenv("TESTING", "1")

    app = FastAPI()
    app.state.accounts_root = clone_root
    app.include_router(compliance.router)

    monkeypatch.setattr(
        "backend.common.compliance.check_trade",
        lambda trade, root: {"owner": trade["owner"]},
    )

    with TestClient(app) as client:
        resp = client.post("/compliance/validate", json={"owner": "demo"})

    assert resp.status_code != 404
    assert resp.status_code == 200
    assert resp.json()["owner"] == "demo"
