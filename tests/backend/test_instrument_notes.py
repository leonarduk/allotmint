from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import instrument_notes as notes
from backend.auth import get_active_user, get_current_user
from backend.routes import instrument_notes as routes


def test_create_list_delete():
    row = notes.create_note("alice", ticker=" rec.l ", stance="BULLISH", text="  Cheap vs peers  ", price="1.25")
    assert row["ticker"] == "REC.L"
    assert row["stance"] == "bullish"
    assert row["text"] == "Cheap vs peers"
    assert row["price"] == 1.25
    assert row["created_at"].endswith("Z")
    assert notes.list_notes("alice") == [row]
    assert notes.list_notes("alice", ticker="rec.l") == [row]
    assert notes.list_notes("alice", ticker="VOD.L") == []
    assert notes.list_notes("bob") == []

    notes.delete_note("alice", row["id"])
    assert notes.list_notes("alice") == []
    with pytest.raises(notes.NoteNotFound):
        notes.delete_note("alice", row["id"])


def test_list_is_newest_first(monkeypatch):
    stamps = iter(["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"])
    monkeypatch.setattr(notes, "_now", lambda: next(stamps))
    older = notes.create_note("alice", ticker="X", stance="bearish", text="first")
    newer = notes.create_note("alice", ticker="X", stance="neutral", text="second")
    assert [n["id"] for n in notes.list_notes("alice")] == [newer["id"], older["id"]]


def test_price_is_optional():
    assert notes.create_note("alice", ticker="X", stance="neutral", text="t")["price"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ticker": "", "stance": "bullish", "text": "t"},
        {"ticker": "X", "stance": "sideways", "text": "t"},
        {"ticker": "X", "stance": "bullish", "text": "   "},
        {"ticker": "X", "stance": "bullish", "text": "t" * (notes.MAX_NOTE_LENGTH + 1)},
        {"ticker": "X", "stance": "bullish", "text": "t", "price": 0},
        {"ticker": "X", "stance": "bullish", "text": "t", "price": "nan"},
    ],
)
def test_create_rejects_invalid(kwargs):
    with pytest.raises(notes.NoteError):
        notes.create_note("alice", **kwargs)


def test_per_user_limit(monkeypatch):
    monkeypatch.setattr(notes, "MAX_NOTES_PER_USER", 1)
    notes.create_note("alice", ticker="X", stance="bullish", text="t")
    with pytest.raises(notes.NoteError):
        notes.create_note("alice", ticker="X", stance="bullish", text="t")
    notes.create_note("bob", ticker="X", stance="bullish", text="t")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_active_user] = lambda: "alice"
    app.dependency_overrides[get_current_user] = lambda: "alice"
    return TestClient(app)


def test_routes_crud(client):
    r = client.post(
        "/instrument-notes/alice", json={"ticker": "rec.l", "stance": "bearish", "text": "Margins slipping"}
    )
    assert r.status_code == 201
    nid = r.json()["id"]

    assert [n["id"] for n in client.get("/instrument-notes/alice", params={"ticker": "REC.L"}).json()] == [nid]
    assert client.get("/instrument-notes/alice", params={"ticker": "VOD.L"}).json() == []

    assert client.delete(f"/instrument-notes/alice/{nid}").json()["status"] == "deleted"
    assert client.delete(f"/instrument-notes/alice/{nid}").status_code == 404


def test_routes_reject_bad_stance_and_other_owner(client):
    assert client.post("/instrument-notes/alice", json={"ticker": "X", "stance": "up", "text": "t"}).status_code == 422
    assert client.get("/instrument-notes/bob").status_code == 403
