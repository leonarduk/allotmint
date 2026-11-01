"""Tests for the /last-visit routes (#11195)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth
from backend.app import create_app
from backend.config import config
from backend.routes import last_visit as routes

ALICE = "alice@example.com"
BOB = "bob@example.com"
URL = "/last-visit/family"


@pytest.fixture
def store_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "last_visit"
    monkeypatch.setenv("LAST_VISIT_STORAGE_URI", str(path))
    return path


@pytest.fixture
def app(store_dir: Path):
    return create_app()


def _client_as(app, user: str, *, demo: bool = False) -> TestClient:
    # Async like the real dependency, so the demo marker it sets reaches the handler.
    async def current_user() -> str:
        auth.demo_readonly.set(demo)
        return user

    app.dependency_overrides[auth.get_current_user] = current_user
    return TestClient(app)


def test_routes_require_auth(monkeypatch: pytest.MonkeyPatch, store_dir: Path) -> None:
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    assert client.post(URL).status_code == 401
    assert client.post(f"{URL}/dismiss").status_code == 401


def test_first_visit_is_stored_with_no_previous(app, store_dir: Path) -> None:
    resp = _client_as(app, ALICE).post(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] is True and body["previous"] is None
    assert datetime.fromisoformat(body["current"]).utcoffset().total_seconds() == 0
    assert (store_dir / f"{routes.last_visit.user_key(ALICE)}.json").exists()


def test_a_seed_carries_the_old_browser_record_over(app) -> None:
    seed = {"previous": None, "current": "2026-01-02T03:04:05Z"}
    body = _client_as(app, ALICE).post(URL, json={"seed": seed}).json()
    assert body["previous"] == "2026-01-02T03:04:05+00:00"


def test_records_are_scoped_to_the_signed_in_user(app) -> None:
    _client_as(app, ALICE).post(URL, json={"seed": {"previous": None, "current": "2026-01-02T03:04:05Z"}})
    assert _client_as(app, BOB).post(URL).json()["previous"] is None


def test_dismiss_clears_previous(app) -> None:
    client = _client_as(app, ALICE)
    client.post(URL, json={"seed": {"previous": None, "current": "2026-01-02T03:04:05Z"}})
    assert client.post(f"{URL}/dismiss").json()["previous"] is None
    assert client.post(URL).json()["previous"] is None


def test_no_identity_is_not_stored_and_not_a_401(app, store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "local_login_email", None)
    client = TestClient(app)
    assert client.post(URL).json() == routes.NOT_STORED
    assert client.post(f"{URL}/dismiss").json() == routes.NOT_STORED
    assert not store_dir.exists()


def test_demo_sessions_never_write(app, store_dir: Path) -> None:
    demo = _client_as(app, ALICE, demo=True)
    assert demo.post(URL).json() == routes.NOT_STORED
    assert demo.post(f"{URL}/dismiss").json() == routes.NOT_STORED
    assert not store_dir.exists()


@pytest.mark.parametrize("slug", ["-leading-dash", "a" * 101, "has space"])
def test_invalid_slugs_are_rejected(app, slug: str) -> None:
    # A bad path parameter is a 400 here (backend/bootstrap/middleware.py), not a 422.
    assert _client_as(app, ALICE).post(f"/last-visit/{slug}").status_code == 400


def test_a_damaged_document_is_503_and_left_alone(app, store_dir: Path) -> None:
    path = store_dir / f"{routes.last_visit.user_key(ALICE)}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    resp = _client_as(app, ALICE).post(URL)
    assert resp.status_code == 503 and resp.json()["code"] == routes.CODE_UNAVAILABLE
    assert path.read_text() == "{not json"
