"""/strategies/{owner} routes (#9653)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common.errors import OwnerNotFoundError, PermissionDeniedError
from backend.routes import rebalance as rebalance_route
from backend.routes import strategies as strategies_route

GB_50_50 = {"equity": 40.0, "long_gilts": 10.0, "intermediate_gilts": 10.0, "short_gilts": 20.0, "gold": 20.0}


@pytest.fixture()
def client(tmp_path):
    accounts = tmp_path / "accounts"
    for owner in ("alex", "bob"):
        (accounts / owner).mkdir(parents=True)
    app = FastAPI()
    app.include_router(strategies_route.router)
    app.include_router(rebalance_route.router)
    app.state.accounts_root = accounts
    client = TestClient(app)
    client.settings_path = accounts / "alex" / "settings.json"
    return client


def _create(client, **body):
    resp = client.post("/strategies/alex", json={"name": "Mine", "targets": {"equity": 100}, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_list_flags_builtins_and_has_no_active_strategy(client):
    body = client.get("/strategies/alex").json()
    ids = [s["id"] for s in body["strategies"]]
    assert ids[:2] == ["60_40", "80_20"]
    assert "golden_butterfly_no_scv_50_50" in ids
    assert "cash_bucket_60_40" not in ids
    assert all(s["builtin"] for s in body["strategies"])
    assert body["active"] is None


def test_get_one_and_unknown(client):
    assert client.get("/strategies/alex/permanent").json()["targets"]["gold"] == 25.0
    assert client.get("/strategies/alex/user-nope").status_code == 404


def test_crud_round_trip(client):
    created = _create(client, description="all in")
    assert created["builtin"] is False
    resp = client.put(
        f"/strategies/alex/{created['id']}", json={"name": "Renamed", "targets": {"equity": 90, "gold": 10}}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed"
    listed = client.get("/strategies/alex").json()["strategies"]
    assert listed[-1]["targets"] == {"equity": 90.0, "gold": 10.0}

    deleted = client.delete(f"/strategies/alex/{created['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "id": created["id"]}
    assert client.get(f"/strategies/alex/{created['id']}").status_code == 404


def test_invalid_strategy_is_400(client):
    resp = client.post("/strategies/alex", json={"name": "Bad", "targets": {"equity": 60}})
    assert resp.status_code == 400
    assert "100%" in resp.json()["detail"]


@pytest.mark.parametrize("method", ["put", "delete"])
def test_builtins_are_read_only(client, method):
    kwargs = {"json": {"name": "Hacked"}} if method == "put" else {}
    resp = getattr(client, method)("/strategies/alex/golden_butterfly", **kwargs)
    assert resp.status_code == 403
    assert "duplicate" in resp.json()["detail"]
    assert client.get("/strategies/alex/golden_butterfly").json()["name"] == "Golden Butterfly"


def test_duplicate_builtin_then_edit_copy(client):
    resp = client.post("/strategies/alex/permanent/duplicate")
    assert resp.status_code == 201, resp.text
    copy = resp.json()
    assert copy["name"] == "Copy of Permanent Portfolio"
    assert copy["builtin"] is False
    edited = client.put(
        f"/strategies/alex/{copy['id']}",
        json={"targets": {"equity": 25, "short_gilts": 25, "long_gilts": 25, "gold": 25}},
    )
    assert edited.status_code == 200
    named = client.post(f"/strategies/alex/{copy['id']}/duplicate", json={"name": "Second"})
    assert named.json()["name"] == "Second"


def test_apply_sets_policy_and_modified_flag(client):
    resp = client.post("/strategies/alex/golden_butterfly_no_scv_50_50/apply")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["policy"]["targets"] == GB_50_50
    assert body["active"]["modified"] is False
    assert client.get("/rebalance/alex/policy").json()["targets"] == GB_50_50

    client.put("/rebalance/alex/policy", json={"targets": {**GB_50_50, "equity": 45, "gold": 15}})
    active = client.get("/strategies/alex").json()["active"]
    assert active["id"] == "golden_butterfly_no_scv_50_50"
    assert active["modified"] is True


def test_apply_unknown_is_404(client):
    assert client.post("/strategies/alex/user-nope/apply").status_code == 404


def test_corrupt_settings_is_409(client):
    client.settings_path.write_text("{oops")
    assert client.post("/strategies/alex", json={"name": "x", "targets": {"equity": 100}}).status_code == 409
    assert client.post("/strategies/alex/60_40/apply").status_code == 409
    assert client.settings_path.read_text() == "{oops"


def test_strategies_are_owner_scoped(client):
    _create(client)
    assert all(s["builtin"] for s in client.get("/strategies/bob").json()["strategies"])
    stored = json.loads(client.settings_path.read_text())
    assert len(stored["strategies"]) == 1


def test_unknown_owner_and_access_denied(client, monkeypatch):
    def deny(identity, owner, root):
        raise PermissionDeniedError("nope")

    with pytest.raises(OwnerNotFoundError):
        client.get("/strategies/nobody")
    monkeypatch.setattr(strategies_route, "ensure_owner_access", deny)
    with pytest.raises(PermissionDeniedError):
        client.get("/strategies/alex")


@pytest.fixture()
def stress_calls(monkeypatch):
    calls = []

    def fake(owner, event, horizons, accounts_root):
        calls.append((owner, event, horizons, accounts_root))
        return {"strategies": [], "portfolio": None}

    monkeypatch.setattr(strategies_route, "stress_strategies", fake)
    return calls


def test_stress_passes_owner_event_and_default_horizons(client, stress_calls):
    resp = client.post("/strategies/alex/stress", json={"date": "2020-02-19"})
    assert resp.status_code == 200, resp.text
    owner, event, horizons, root = stress_calls[0]
    assert owner == "alex"
    assert event["date"] == "2020-02-19"
    assert horizons == {"1m": 30, "3m": 90, "1y": 365}
    assert root == client.settings_path.parent.parent


def test_stress_parses_horizons_like_the_scenario_route(client, stress_calls):
    resp = client.post("/strategies/alex/stress", json={"date": "2020-02-19", "horizons": ["1w,60"]})
    assert resp.status_code == 200, resp.text
    assert stress_calls[0][2] == {"1w": 7, "60": 60}


@pytest.mark.parametrize(
    "body, status",
    [
        ({}, 400),  # no event
        ({"date": "not-a-date"}, 400),
        ({"event_id": "no-such-event"}, 404),
        ({"date": "2020-02-19", "horizons": []}, 400),
        ({"date": "2020-02-19", "horizons": ["0"]}, 400),
        ({"date": "2020-02-19", "horizons": ["4000"]}, 400),
        ({"date": "2020-02-19", "horizons": ["1d", "1w", "1m", "3m", "1y", "2", "3"]}, 400),
    ],
)
def test_stress_rejects_bad_input(client, stress_calls, body, status):
    assert client.post("/strategies/alex/stress", json=body).status_code == status
    assert stress_calls == []


def test_stress_is_owner_checked(client, stress_calls, monkeypatch):
    def deny(identity, owner, root):
        raise PermissionDeniedError("nope")

    with pytest.raises(OwnerNotFoundError):
        client.post("/strategies/nobody/stress", json={"date": "2020-02-19"})
    monkeypatch.setattr(strategies_route, "ensure_owner_access", deny)
    with pytest.raises(PermissionDeniedError):
        client.post("/strategies/alex/stress", json={"date": "2020-02-19"})
    assert stress_calls == []
