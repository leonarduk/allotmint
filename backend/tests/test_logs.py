from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import config
from backend.routes.logs import router


def create_app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_logs_endpoint_returns_content(tmp_path, monkeypatch):
    log_file = tmp_path / "backend.log"
    log_file.write_text("line1\nline2\n", encoding="utf-8")
    monkeypatch.setattr(config, "repo_root", tmp_path)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/logs")
    assert resp.status_code == 200
    assert "line2" in resp.text


def test_logs_endpoint_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", tmp_path)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/logs")
    assert resp.status_code == 404
