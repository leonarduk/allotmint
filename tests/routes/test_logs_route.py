from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.config import config
from backend.routes.logs import router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with repo_root isolated to tmp_path."""
    monkeypatch.setattr(config, "repo_root", tmp_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture()
def log_file(tmp_path):
    path = tmp_path / "backend.log"
    yield path
    if path.exists():
        path.unlink()


def test_returns_last_three_lines(client, log_file):
    log_file.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    resp = client.get("/logs", params={"lines": 3})
    assert resp.status_code == 200
    assert resp.text.strip().splitlines() == ["line3", "line4", "line5"]
    log_file.unlink()
    assert not log_file.exists()


def test_missing_file_returns_404(client, log_file):
    resp = client.get("/logs")
    assert resp.status_code == 404
    assert not log_file.exists()
