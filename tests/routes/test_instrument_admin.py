import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from typing import Any

import backend.routes.instrument_admin as instrument_admin


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(instrument_admin.router)
    return TestClient(app)


def test_list_instrument_metadata(monkeypatch):
    monkeypatch.setattr(
        instrument_admin,
        "list_instruments",
        lambda: [{"ticker": "ABC.L", "grouping": "Income"}],
    )
    client = make_client()
    resp = client.get("/instrument/admin")
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "ABC.L", "grouping": "Income"}]


def test_list_group_labels_merges_catalogue(monkeypatch):
    monkeypatch.setattr(instrument_admin, "list_instruments", lambda: [{"grouping": "Income"}, {"grouping": "Growth"}])
    monkeypatch.setattr(
        instrument_admin.instrument_groups,
        "load_groups",
        lambda: ["Income", "Speculative"],
    )
    client = make_client()
    resp = client.get("/instrument/admin/groups")
    assert resp.status_code == 200
    assert resp.json() == ["Growth", "Income", "Speculative"]


def test_create_group_adds_new_label(monkeypatch):
    added: dict[str, str] = {}

    def fake_load():
        return ["Existing"]

    def fake_add(name: str):
        added["name"] = name
        return ["Existing", name]

    monkeypatch.setattr(instrument_admin.instrument_groups, "load_groups", fake_load)
    monkeypatch.setattr(instrument_admin.instrument_groups, "add_group", fake_add)
    client = make_client()
    resp = client.post("/instrument/admin/groups", json={"name": "Income"})
    assert resp.status_code == 200
    assert added["name"] == "Income"
    assert resp.json() == {
        "status": "created",
        "group": "Income",
        "groups": ["Existing", "Income"],
    }


def test_create_group_rejects_invalid(monkeypatch):
    monkeypatch.setattr(instrument_admin.instrument_groups, "load_groups", lambda: [])
    client = make_client()
    resp = client.post("/instrument/admin/groups", json={"name": "   "})
    assert resp.status_code == 400


def test_get_instrument_ok(monkeypatch, tmp_path):
    def fake_path(t, e):
        return tmp_path / f"{e}" / f"{t}.json"

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(
        instrument_admin, "get_instrument_meta", lambda t: {"ticker": t}
    )
    client = make_client()
    resp = client.get("/instrument/admin/L/ABC")
    assert resp.status_code == 200
    assert resp.json() == {"ticker": "ABC.L"}


def test_get_instrument_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(
        instrument_admin,
        "instrument_meta_path",
        lambda t, e: tmp_path / f"{e}" / f"{t}.json",
    )
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", lambda t: {})
    client = make_client()
    resp = client.get("/instrument/admin/L/ABC")
    assert resp.status_code == 404


def test_get_instrument_invalid(monkeypatch):
    def bad_path(*_):
        raise ValueError("bad ticker")

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", bad_path)
    client = make_client()
    resp = client.get("/instrument/admin/L/ABC")
    assert resp.status_code == 400


def test_post_instrument_create(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    saved = {}

    def fake_save(t, e, body):
        saved["ticker"] = f"{t}.{e}"
        saved["body"] = body

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    client = make_client()
    resp = client.post(
        "/instrument/admin/L/ABC", json={"ticker": "ABC.L", "grouping": "Income"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "created"}
    assert saved["ticker"] == "ABC.L"
    assert saved["body"]["grouping"] == "Income"


def test_assign_group_updates_metadata(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    saved: dict[str, Any] = {}

    def fake_save(t, e, body):
        saved["ticker"] = f"{t}.{e}"
        saved["body"] = body

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", lambda t: {"ticker": t, "name": "Test"})
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    monkeypatch.setattr(instrument_admin.instrument_groups, "add_group", lambda name: [name])
    client = make_client()
    resp = client.post("/instrument/admin/L/ABC/group", json={"group": "Growth"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "assigned", "group": "Growth", "groups": ["Growth"]}
    assert saved["ticker"] == "ABC.L"
    assert saved["body"]["grouping"] == "Growth"
    assert saved["body"]["name"] == "Test"


def test_assign_group_invalid_body(monkeypatch, tmp_path):
    monkeypatch.setattr(
        instrument_admin,
        "instrument_meta_path",
        lambda t, e: tmp_path / f"{e}" / f"{t}.json",
    )
    client = make_client()
    resp = client.post("/instrument/admin/L/ABC/group", json={"group": "  "})
    assert resp.status_code == 400


def test_post_instrument_conflict(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
        return p

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", lambda *a, **k: None)
    client = make_client()
    resp = client.post("/instrument/admin/L/ABC", json={"ticker": "ABC.L"})
    assert resp.status_code == 409


def test_post_instrument_invalid(monkeypatch):
    monkeypatch.setattr(
        instrument_admin,
        "instrument_meta_path",
        lambda *a: (_ for _ in ()).throw(ValueError("bad")),
    )
    client = make_client()
    resp = client.post("/instrument/admin/L/ABC", json={"ticker": "ABC.L"})
    assert resp.status_code == 400


def test_post_instrument_ticker_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        instrument_admin,
        "instrument_meta_path",
        lambda t, e: tmp_path / f"{e}" / f"{t}.json",
    )
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", lambda *a, **k: None)
    client = make_client()
    resp = client.post("/instrument/admin/L/ABC", json={"ticker": "DEF.L"})
    assert resp.status_code == 400


def test_put_instrument_update(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
        return p

    saved = {}

    def fake_save(t, e, body):
        saved["ticker"] = f"{t}.{e}"
        saved["body"] = body

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    client = make_client()
    resp = client.put(
        "/instrument/admin/L/ABC", json={"ticker": "ABC.L", "grouping": "Income"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "updated"}
    assert saved["ticker"] == "ABC.L"
    assert saved["body"]["grouping"] == "Income"


def test_clear_group_updates_metadata(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    saved: dict[str, Any] = {}

    def fake_save(t, e, body):
        saved["ticker"] = f"{t}.{e}"
        saved["body"] = body

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(
        instrument_admin,
        "get_instrument_meta",
        lambda t: {"ticker": t, "grouping": "Old", "name": "Test"},
    )
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    client = make_client()
    resp = client.delete("/instrument/admin/L/ABC/group")
    assert resp.status_code == 200
    assert resp.json() == {"status": "cleared"}
    assert "grouping" not in saved["body"]


def test_clear_group_noop_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        instrument_admin,
        "instrument_meta_path",
        lambda t, e: tmp_path / f"{e}" / f"{t}.json",
    )
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", lambda t: {})
    called = {"value": False}

    def fake_save(*_args, **_kwargs):
        called["value"] = True

    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    client = make_client()
    resp = client.delete("/instrument/admin/L/ABC/group")
    assert resp.status_code == 200
    assert resp.json() == {"status": "cleared"}
    assert called["value"] is False


def test_put_instrument_not_found(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", lambda *a, **k: None)
    client = make_client()
    resp = client.put("/instrument/admin/L/ABC", json={"ticker": "ABC.L"})
    assert resp.status_code == 404


def test_put_instrument_invalid(monkeypatch):
    monkeypatch.setattr(
        instrument_admin, "instrument_meta_path", lambda *a: (_ for _ in ()).throw(ValueError("bad"))
    )
    client = make_client()
    resp = client.put("/instrument/admin/L/ABC", json={"ticker": "ABC.L"})
    assert resp.status_code == 400


def test_put_instrument_ticker_mismatch(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
        return p

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", lambda *a, **k: None)
    client = make_client()
    resp = client.put("/instrument/admin/L/ABC", json={"ticker": "DEF.L"})
    assert resp.status_code == 400


def test_delete_instrument_ok(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
        return p

    deleted = {}

    def fake_delete(t, e):
        deleted["ticker"] = f"{t}.{e}"

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "delete_instrument_meta", fake_delete)
    client = make_client()
    resp = client.delete("/instrument/admin/L/ABC")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}
    assert deleted["ticker"] == "ABC.L"


def test_delete_instrument_not_found(monkeypatch, tmp_path):
    def fake_path(t, e):
        p = tmp_path / f"{e}" / f"{t}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_path)
    monkeypatch.setattr(instrument_admin, "delete_instrument_meta", lambda *a, **k: None)
    client = make_client()
    resp = client.delete("/instrument/admin/L/ABC")
    assert resp.status_code == 404


def test_delete_instrument_invalid(monkeypatch):
    monkeypatch.setattr(
        instrument_admin, "instrument_meta_path", lambda *a: (_ for _ in ()).throw(ValueError("bad"))
    )
    client = make_client()
    resp = client.delete("/instrument/admin/L/ABC")
    assert resp.status_code == 400
