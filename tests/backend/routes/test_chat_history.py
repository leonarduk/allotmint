"""Tests for the /chat/conversation routes (#8870)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth
from backend.app import create_app
from backend.config import config
from backend.routes import chat_history as routes

ALICE = "alice@example.com"
BOB = "bob@example.com"
URL = "/chat/conversation"


def _conversation(*contents: str) -> dict:
    nodes, active, parent = [], {}, None
    for i, content in enumerate(contents, start=1):
        node_id = str(i)
        nodes.append({"id": node_id, "parentId": parent, "role": "user" if i % 2 else "assistant", "content": content})
        active[parent or "root"] = node_id
        parent = node_id
    return {"nodes": nodes, "active": active, "nextId": len(contents) + 1}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAT_HISTORY_STORAGE_URI", str(tmp_path / "chat"))
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
    monkeypatch.setenv("CHAT_HISTORY_STORAGE_URI", str(tmp_path))
    client = TestClient(create_app())
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"revision": 0, "conversation": _conversation("x")}).status_code == 401
    assert client.post(f"{URL}/archive").status_code == 401
    assert client.delete(URL).status_code == 401


def test_get_without_a_saved_conversation(app) -> None:
    resp = _client_as(app, ALICE).get(URL)
    assert resp.status_code == 200
    assert resp.json() == {
        "owner": routes.chat_history.user_key(ALICE),
        "revision": 0,
        "conversation": {"nodes": [], "active": {}, "nextId": 1},
    }


def test_owner_is_a_per_user_hash_not_the_email(app) -> None:
    alice_owner = _client_as(app, ALICE).get(URL).json()["owner"]
    bob_owner = _client_as(app, BOB).get(URL).json()["owner"]
    assert alice_owner != bob_owner
    assert "alice" not in alice_owner and "@" not in alice_owner


def test_put_then_get_round_trips_the_tree_with_versions(app) -> None:
    client = _client_as(app, ALICE)
    tree = _conversation("q", "a")
    # A second version of the reply, selected.
    tree["nodes"].append({"id": "3", "parentId": "1", "role": "assistant", "content": "a2"})
    tree["active"]["1"] = "3"
    tree["nextId"] = 4

    resp = client.put(URL, json={"revision": 0, "conversation": tree})
    assert resp.status_code == 200 and resp.json() == {"revision": 1}

    assert client.get(URL).json() == {"owner": routes.chat_history.user_key(ALICE), "revision": 1, "conversation": tree}


def test_stale_revision_is_409_with_the_current_document(app) -> None:
    client = _client_as(app, ALICE)
    client.put(URL, json={"revision": 0, "conversation": _conversation("tab 1")})

    resp = client.put(URL, json={"revision": 0, "conversation": _conversation("tab 2")})

    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "chat_conversation_conflict"
    assert body["current"]["revision"] == 1
    assert body["current"]["conversation"]["nodes"][0]["content"] == "tab 1"


def test_users_cannot_reach_each_others_conversation(app) -> None:
    alice = _client_as(app, ALICE)
    alice.put(URL, json={"revision": 0, "conversation": _conversation("alice's holdings")})

    bob = _client_as(app, BOB)
    assert bob.get(URL).json()["revision"] == 0
    # Bob writing at Alice's revision, archiving and deleting only touch his own document.
    assert bob.put(URL, json={"revision": 1, "conversation": _conversation("bob")}).status_code == 409
    assert bob.post(f"{URL}/archive").json() == {"revision": 0, "archived": False}
    assert bob.delete(URL).status_code == 204

    alice = _client_as(app, ALICE)
    assert alice.get(URL).json()["conversation"]["nodes"][0]["content"] == "alice's holdings"


def test_demo_sessions_read_nothing_and_cannot_write(app) -> None:
    _client_as(app, ALICE).put(URL, json={"revision": 0, "conversation": _conversation("real")})

    demo = _client_as(app, ALICE, demo=True)
    assert demo.get(URL).json()["revision"] == 0
    assert demo.put(URL, json={"revision": 1, "conversation": _conversation("x")}).status_code == 403
    assert demo.post(f"{URL}/archive").status_code == 403
    assert demo.delete(URL).status_code == 403

    assert _client_as(app, ALICE).get(URL).json()["revision"] == 1


def test_archive_starts_an_empty_conversation(app) -> None:
    client = _client_as(app, ALICE)
    client.put(URL, json={"revision": 0, "conversation": _conversation("old")})

    assert client.post(f"{URL}/archive").json() == {"revision": 2, "archived": True}
    body = client.get(URL).json()
    assert (body["revision"], body["conversation"]) == (2, {"nodes": [], "active": {}, "nextId": 1})


def test_delete_removes_current_and_archived(app, tmp_path: Path) -> None:
    client = _client_as(app, ALICE)
    client.put(URL, json={"revision": 0, "conversation": _conversation("old")})
    client.post(f"{URL}/archive")
    client.put(URL, json={"revision": 2, "conversation": _conversation("new")})

    assert client.delete(URL).status_code == 204
    assert client.get(URL).json()["revision"] == 0
    assert not any((tmp_path / "chat").iterdir())


@pytest.mark.parametrize(
    "conversation",
    [
        {"nodes": [{"id": "1", "parentId": None, "role": "system", "content": "x"}], "active": {}, "nextId": 2},
        {"nodes": [{"id": "1", "parentId": "9", "role": "user", "content": "x"}], "active": {}, "nextId": 2},
        {
            "nodes": [
                {"id": "1", "parentId": None, "role": "user", "content": "x"},
                {"id": "1", "parentId": None, "role": "user", "content": "y"},
            ],
            "active": {},
            "nextId": 3,
        },
        {"nodes": [{"id": "1", "parentId": None, "role": "user", "content": "x"}], "active": {"1": "1"}, "nextId": 2},
        {
            "nodes": [{"id": "1", "parentId": None, "role": "user", "content": "x"}],
            "active": {"root": "2"},
            "nextId": 2,
        },
    ],
    ids=["bad-role", "missing-parent", "duplicate-id", "active-not-a-child", "active-unknown"],
)
def test_malformed_trees_are_422(app, conversation) -> None:
    resp = _client_as(app, ALICE).put(URL, json={"revision": 0, "conversation": conversation})
    assert resp.status_code == 422


def test_parent_must_precede_child(app) -> None:
    conversation = {
        "nodes": [
            {"id": "2", "parentId": "1", "role": "assistant", "content": "a"},
            {"id": "1", "parentId": None, "role": "user", "content": "q"},
        ],
        "active": {},
        "nextId": 3,
    }
    resp = _client_as(app, ALICE).put(URL, json={"revision": 0, "conversation": conversation})
    assert resp.status_code == 422


def test_limits_are_413(app, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_as(app, ALICE)
    monkeypatch.setattr(routes, "MAX_NODES", 2)
    assert client.put(URL, json={"revision": 0, "conversation": _conversation("a", "b", "c")}).status_code == 413

    monkeypatch.setattr(routes, "MAX_CONTENT_CHARS", 5)
    assert client.put(URL, json={"revision": 0, "conversation": _conversation("too long")}).status_code == 413

    monkeypatch.setattr(routes, "MAX_DOCUMENT_BYTES", 50)
    body = json.dumps({"revision": 0, "conversation": _conversation("abc")})
    assert len(body) > 50
    assert client.put(URL, content=body, headers={"Content-Type": "application/json"}).status_code == 413

    # A declared oversize body is refused before it is read.
    resp = client.put(URL, content=b"{}", headers={"Content-Type": "application/json", "Content-Length": "999999999"})
    assert resp.status_code == 413

    # Nothing was written by any of the refused saves.
    assert client.get(URL).json()["revision"] == 0


def test_storage_failure_is_503_with_a_code(app, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args, **_kwargs):
        raise routes.chat_history.ChatHistoryUnavailable("S3 read failed")

    for name in ("load_conversation", "save_conversation", "archive_conversation", "delete_history"):
        monkeypatch.setattr(routes.chat_history, name, broken)
    client = _client_as(app, ALICE)

    responses = [
        client.get(URL),
        client.put(URL, json={"revision": 0, "conversation": _conversation("x")}),
        client.post(f"{URL}/archive"),
        client.delete(URL),
    ]
    assert [r.status_code for r in responses] == [503] * 4
    assert all(r.json()["code"] == "chat_history_unavailable" for r in responses)
