"""Tests for the /watchlists routes (#10713)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth
from backend.app import create_app
from backend.config import config
from backend.routes import watchlists as routes

ALICE = "alice@example.com"
BOB = "bob@example.com"
URL = "/watchlists"


def _state(name: str = "My watchlist", symbols: list[str] | None = None) -> dict:
    return {"activeId": "default", "lists": [{"id": "default", "name": name, "symbols": symbols or ["^FTSE"]}]}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WATCHLISTS_STORAGE_URI", str(tmp_path / "watchlists"))
    return create_app()


def _client_as(app, user: str, *, demo: bool = False) -> TestClient:
    # Async like the real dependency, so the demo marker it sets reaches the handler.
    async def current_user() -> str:
        auth.demo_readonly.set(demo)
        return user

    app.dependency_overrides[auth.get_current_user] = current_user
    return TestClient(app)


def test_routes_require_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"revision": 0, "state": _state()}).status_code == 401


def test_no_identity_reads_nothing_and_cannot_write_without_a_401(app, monkeypatch: pytest.MonkeyPatch) -> None:
    # Auth disabled and no local login override: a 401 would sign the SPA out.
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "local_login_email", None)
    client = TestClient(app)
    assert client.get(URL).json() == {"owner": None, "revision": 0, "state": None}
    assert client.put(URL, json={"revision": 0, "state": _state()}).status_code == 403


def test_get_without_saved_watchlists(app) -> None:
    resp = _client_as(app, ALICE).get(URL)
    assert resp.status_code == 200
    assert resp.json() == {"owner": routes.watchlists.user_key(ALICE), "revision": 0, "state": None}


def test_put_then_get_round_trips_for_the_same_user_only(app, tmp_path: Path) -> None:
    alice = _client_as(app, ALICE)
    state = _state("Tech", ["AAPL", "MSFT"])
    resp = alice.put(URL, json={"revision": 0, "state": state})
    assert resp.status_code == 200
    assert resp.json() == {"revision": 1, "state": state}
    assert alice.get(URL).json()["state"] == state
    assert (tmp_path / "watchlists" / f"{routes.watchlists.user_key(ALICE)}.json").exists()

    assert _client_as(app, BOB).get(URL).json()["state"] is None


def test_stale_revision_is_409_with_the_current_copy(app) -> None:
    client = _client_as(app, ALICE)
    client.put(URL, json={"revision": 0, "state": _state("Phone")})

    resp = client.put(URL, json={"revision": 0, "state": _state("Laptop")})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == routes.CODE_CONFLICT
    assert body["current"]["revision"] == 1
    assert body["current"]["state"]["lists"][0]["name"] == "Phone"


def test_demo_sessions_read_nothing_and_cannot_write(app) -> None:
    _client_as(app, ALICE).put(URL, json={"revision": 0, "state": _state()})

    demo = _client_as(app, ALICE, demo=True)
    assert demo.get(URL).json()["state"] is None
    assert demo.put(URL, json={"revision": 1, "state": _state("x")}).status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"revision": -1, "state": _state()},
        {"revision": 0},
        {"revision": 0, "state": {"activeId": "default", "lists": []}},
        {"revision": 0, "state": {"activeId": "other", "lists": _state()["lists"]}},
    ],
)
def test_invalid_bodies_are_422(app, body) -> None:
    assert _client_as(app, ALICE).put(URL, json=body).status_code == 422


def test_oversize_body_is_413(app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "MAX_DOCUMENT_BYTES", 50)
    resp = _client_as(app, ALICE).put(URL, json={"revision": 0, "state": _state("x" * 60)})
    assert resp.status_code == 413


def test_a_damaged_saved_copy_is_503_and_is_left_alone(app, tmp_path: Path) -> None:
    path = tmp_path / "watchlists" / f"{routes.watchlists.user_key(ALICE)}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    client = _client_as(app, ALICE)

    get = client.get(URL)
    assert get.status_code == 503 and get.json()["code"] == routes.CODE_UNAVAILABLE
    assert client.put(URL, json={"revision": 0, "state": _state()}).status_code == 503
    assert path.read_text() == "{not json"
