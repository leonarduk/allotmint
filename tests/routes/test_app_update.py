"""Tests for the local-only self-update route (backend/routes/app_update.py).

Uses real throwaway git repositories (a bare "origin" plus a clone acting as
the running checkout) rather than mocking subprocess, so the fast-forward and
refusal paths are exercised against actual git behaviour.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.app_update as app_update
from backend.bootstrap.routers import register_routers


def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, path: str, content: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _run(repo, "add", path)
    _run(repo, "commit", "-q", "-m", f"update {path}")


@pytest.fixture
def repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Return ``(checkout, upstream_worktree)``; the checkout tracks origin/main."""

    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(key, value)
    origin = tmp_path / "origin.git"
    _run(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    upstream = tmp_path / "upstream"
    _run(tmp_path, "clone", "-q", str(origin), str(upstream))
    _run(upstream, "checkout", "-q", "-b", "main")
    _commit(upstream, "README.md", "v1\n")
    _run(upstream, "push", "-q", "-u", "origin", "main")
    checkout = tmp_path / "checkout"
    _run(tmp_path, "clone", "-q", str(origin), str(checkout))
    monkeypatch.setattr(app_update.config, "repo_root", checkout)
    monkeypatch.setattr(app_update.config, "disable_auth", True)
    return checkout, upstream


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(app_update.router)
    return TestClient(app)


def test_status_reports_up_to_date(repos):
    resp = _client().get("/support/app-update/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["branch"] == "main"
    assert body["upstream"] == "origin/main"
    assert body["behind"] == 0
    assert body["can_update"] is False
    assert body["reason"] == "Already up to date."


def test_update_fast_forwards_and_flags_dependencies(repos):
    checkout, upstream = repos
    _commit(upstream, "backend/foo.py", "x = 1\n")
    _commit(upstream, "frontend/package.json", "{}\n")
    _run(upstream, "push", "-q")
    client = _client()

    status = client.get("/support/app-update/status").json()
    assert status["behind"] == 2
    assert status["can_update"] is True

    resp = client.post("/support/app-update")
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] is True
    assert body["current_commit"] == _run(upstream, "rev-parse", "HEAD")
    assert sorted(body["changed_files"]) == ["backend/foo.py", "frontend/package.json"]
    assert body["dependencies_changed"] == ["frontend/package.json"]
    assert body["backend_changed"] is True
    assert body["frontend_changed"] is True
    assert (checkout / "backend" / "foo.py").exists()


def test_update_refuses_dirty_tree(repos):
    checkout, upstream = repos
    _commit(upstream, "README.md", "v2\n")
    _run(upstream, "push", "-q")
    (checkout / "README.md").write_text("local edit\n", encoding="utf-8")

    resp = _client().post("/support/app-update")
    assert resp.status_code == 409
    assert "uncommitted changes" in resp.json()["detail"]
    assert (checkout / "README.md").read_text(encoding="utf-8") == "local edit\n"


def test_update_refuses_diverged_branch(repos):
    checkout, upstream = repos
    _commit(upstream, "README.md", "v2\n")
    _run(upstream, "push", "-q")
    _commit(checkout, "local.txt", "mine\n")
    before = _run(checkout, "rev-parse", "HEAD")

    resp = _client().post("/support/app-update")
    assert resp.status_code == 409
    assert "cannot be fast-forwarded" in resp.json()["detail"]
    assert _run(checkout, "rev-parse", "HEAD") == before


def test_status_without_git_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(app_update.config, "repo_root", tmp_path)
    monkeypatch.setattr(app_update.config, "disable_auth", True)
    body = _client().get("/support/app-update/status").json()
    assert body["can_update"] is False
    assert body["reason"] == "Not running from a git checkout."


def test_requires_owner_when_auth_enabled(repos, monkeypatch):
    monkeypatch.setattr(app_update.config, "disable_auth", False)
    monkeypatch.setattr(app_update.config, "allowed_emails", ["owner@example.com"])
    app = FastAPI()
    app.include_router(app_update.router)
    app.dependency_overrides[app_update.get_active_user] = lambda: "someone@example.com"
    assert TestClient(app).post("/support/app-update").status_code == 403


@pytest.mark.parametrize(("app_env", "expected_status"), [("local", 200), ("aws", 404)])
def test_route_only_registered_for_local(app_env, expected_status, tmp_path, monkeypatch):
    cfg = app_update.config
    monkeypatch.setattr(cfg, "app_env", app_env)
    monkeypatch.setattr(cfg, "disable_auth", True)
    monkeypatch.setattr(cfg, "repo_root", tmp_path)
    app = FastAPI()
    app.state.limiter = None
    with pytest.warns(RuntimeWarning):  # bare app: chat/signup routers warn about missing rate limits
        register_routers(app, cfg)
    assert TestClient(app).get("/support/app-update/status").status_code == expected_status
