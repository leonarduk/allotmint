from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import pytest

import backend.routes.nudges as nudges


def make_client(tmp_path, monkeypatch, owners=None) -> TestClient:
    app = FastAPI()
    app.include_router(nudges.router)
    app.state.accounts_root = tmp_path

    owners = owners or ["alice"]

    monkeypatch.setattr(
        nudges.data_loader,
        "list_plots",
        lambda root: [{"owner": owner} for owner in owners],
    )

    return TestClient(app)


def test_validate_owner_unknown_user(tmp_path, monkeypatch):
    app = FastAPI()
    app.state.accounts_root = tmp_path
    monkeypatch.setattr(
        nudges.data_loader,
        "list_plots",
        lambda root: [{"owner": "alice"}],
    )
    request = Request({"type": "http", "app": app})
    with pytest.raises(HTTPException):
        nudges._validate_owner("bob", request)

    # Allowing unknown users should not raise
    nudges._validate_owner("bob", request, allow_unknown=True)


def test_subscribe_calls_set_user_nudge(tmp_path, monkeypatch):
    called = {}

    def fake_set_user_nudge(user, freq, snooze_until):
        called["args"] = (user, freq, snooze_until)

    monkeypatch.setattr(nudges.nudge_utils, "set_user_nudge", fake_set_user_nudge)

    client = make_client(tmp_path, monkeypatch, owners=[])
    resp = client.post(
        "/nudges/subscribe",
        json={"user": "bob", "frequency": 7, "snooze_until": "2024-01-01"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert called["args"] == ("bob", 7, "2024-01-01")


def test_snooze_calls_snooze_user(tmp_path, monkeypatch):
    called = {}

    def fake_snooze_user(user, days):
        called["args"] = (user, days)

    monkeypatch.setattr(nudges.nudge_utils, "snooze_user", fake_snooze_user)

    client = make_client(tmp_path, monkeypatch, owners=[])
    resp = client.post("/nudges/snooze", json={"user": "bob", "days": 3})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert called["args"] == ("bob", 3)


def test_list_nudges_gets_recent_nudges(tmp_path, monkeypatch):
    nudges_list = [{"id": 1}]
    monkeypatch.setattr(
        nudges.nudge_utils, "get_recent_nudges", lambda limit=50: nudges_list
    )
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/nudges/")
    assert resp.status_code == 200
    assert resp.json() == nudges_list
