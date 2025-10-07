import asyncio
import importlib

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.config import config


# Helper ----------------------------------------------------------------------

def _build_app(tmp_path, monkeypatch) -> FastAPI:
    """Return a FastAPI app with quests storage isolated to ``tmp_path``."""

    monkeypatch.setenv("QUESTS_URI", f"file://{tmp_path/'quests.json'}")
    import backend.quests
    import backend.routes.quest_routes as quest_routes

    importlib.reload(backend.quests)
    importlib.reload(quest_routes)

    app = FastAPI()
    app.include_router(quest_routes.router)
    return app


def _client_for(user: str, tmp_path, monkeypatch) -> TestClient:
    app = _build_app(tmp_path, monkeypatch)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# Tests -----------------------------------------------------------------------

def test_complete_quest_success(tmp_path, monkeypatch):
    """Completing a valid quest returns updated progress."""
    client = _client_for("alice", tmp_path, monkeypatch)
    resp = client.post("/quests/check_in/complete")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp"] == 10
    statuses = {q["id"]: q["completed"] for q in data["quests"]}
    assert statuses["check_in"] is True
    assert statuses["read_article"] is False


def test_complete_nonexistent_quest_returns_404(tmp_path, monkeypatch):
    """POSTing a nonexistent quest ID returns a 404 error."""
    client = _client_for("alice", tmp_path, monkeypatch)
    resp = client.post("/quests/nonexistent_id/complete")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Quest not found"}


def test_today_returns_quests_for_authenticated_user(tmp_path, monkeypatch):
    """Dependency overrides continue to flow through active user resolution."""

    client = _client_for("bob", tmp_path, monkeypatch)
    resp = client.get("/quests/today")
    assert resp.status_code == 200
    data = resp.json()
    assert {quest["id"] for quest in data["quests"]} == {"check_in", "read_article"}
    assert data["xp"] == 0


def test_today_returns_401_when_user_missing(tmp_path, monkeypatch):
    """Requests without an authenticated user receive a 401 error."""

    monkeypatch.setattr(config, "disable_auth", False)
    app = _build_app(tmp_path, monkeypatch)
    app.dependency_overrides[get_current_user] = lambda: None
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/quests/today")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


def test_today_uses_override_when_active_user_returns_none(tmp_path, monkeypatch):
    """Overrides for ``get_current_user`` apply when active user resolution fails."""

    import backend.routes.quest_routes as quest_routes

    monkeypatch.setattr(config, "disable_auth", False)
    app = _build_app(tmp_path, monkeypatch)

    async def _no_active_user(_: Request):
        return None

    app.dependency_overrides[quest_routes.get_active_user] = _no_active_user
    app.dependency_overrides[get_current_user] = lambda: "carol"

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/quests/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp"] == 0


def test_today_falls_back_to_demo_when_auth_disabled(tmp_path, monkeypatch):
    """Requests succeed in demo mode even without explicit authentication."""

    monkeypatch.setattr(config, "disable_auth", True)
    app = _build_app(tmp_path, monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/quests/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp"] == 0


def test_require_active_user_handles_coroutine_override(tmp_path, monkeypatch):
    """Coroutine overrides for ``get_current_user`` are awaited."""

    import backend.routes.quest_routes as quest_routes

    monkeypatch.setattr(config, "disable_auth", False)
    app = _build_app(tmp_path, monkeypatch)

    async def _inactive(_: Request):
        return None

    async def _async_override():
        await asyncio.sleep(0)
        return "dave"

    app.dependency_overrides[quest_routes.get_active_user] = _inactive
    app.dependency_overrides[get_current_user] = _async_override

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/quests/today")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["xp"] == 0
