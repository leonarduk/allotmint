"""GET/PUT /plans/{owner} (#9547)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import investment_plan as plan_mod
from backend.common.errors import OwnerNotFoundError, PermissionDeniedError
from backend.routes import investment_plan as plan_route

PLAN = {
    "owner": "alex",
    "updated": "2026-10-06",
    "summary": "60/40",
    "target": [{"class": "equity", "weight_pct": 60}, {"class": "long_gilts", "weight_pct": 40}],
    "vehicles": {"long_gilts": ["GLTL.L"]},
    "review": {"next_review": "2027-10-06", "triggers": ["drift > 5pp"]},
}


@pytest.fixture()
def data_root(monkeypatch, tmp_path):
    accounts = tmp_path / "accounts"
    for owner in ("alex", "bob"):
        (accounts / owner).mkdir(parents=True)
    (accounts / "alex" / "person.json").write_text(json.dumps({"owner": "alex"}))
    # Point the configured data root elsewhere: the route must use the request's accounts root.
    monkeypatch.setattr(plan_mod.config, "data_root", tmp_path / "elsewhere", raising=False)
    monkeypatch.setattr(plan_mod, "get_instrument_meta", lambda ticker: {"ticker": ticker})
    return tmp_path


def _client(data_root, raise_server_exceptions=True):
    app = FastAPI()
    app.include_router(plan_route.router)
    app.state.accounts_root = data_root / "accounts"
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_missing_plan_is_404_with_clear_message(data_root):
    resp = _client(data_root).get("/plans/alex")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No investment plan saved for alex"


def test_put_then_get_round_trip(data_root):
    client = _client(data_root)
    resp = client.put("/plans/alex", json=PLAN)
    assert resp.status_code == 200, resp.text
    assert (data_root / "plans" / "alex.json").exists()

    body = client.get("/plans/alex").json()
    assert body["plan"]["summary"] == "60/40"
    assert body["plan"]["status"] == "draft"
    assert body["plan"]["target"][1] == {"class": "long_gilts", "weight_pct": 40.0}
    assert body["warnings"] == []
    assert body["rebalance"]["rebalance_targets"] == {}
    assert body["rebalance"]["matches"] is False


@pytest.mark.parametrize("owner_field", ["missing", None])
def test_put_defaults_owner_from_path(data_root, owner_field):
    payload = {k: v for k, v in PLAN.items() if k != "owner"}
    if owner_field is None:
        payload["owner"] = None
    resp = _client(data_root).put("/plans/alex", json=payload)
    assert resp.status_code == 200
    assert resp.json()["plan"]["owner"] == "alex"


def test_plan_stored_beside_request_accounts_root(data_root):
    _client(data_root).put("/plans/alex", json=PLAN)
    assert (data_root / "plans" / "alex.json").exists()
    assert not (data_root / "elsewhere").exists()


def test_put_does_not_write_when_response_fails(data_root, monkeypatch):
    def boom(owner, root):
        raise RuntimeError("policy unavailable")

    monkeypatch.setattr(plan_route, "load_allocation_policy", boom)
    with pytest.raises(RuntimeError):
        _client(data_root).put("/plans/alex", json=PLAN)
    assert not (data_root / "plans" / "alex.json").exists()


def test_put_rejects_missing_target(data_root):
    payload = {k: v for k, v in PLAN.items() if k != "target"}
    resp = _client(data_root).put("/plans/alex", json=payload)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "target: Field required"


def test_put_rejects_bad_weight_sum(data_root):
    bad = {**PLAN, "target": [{"class": "equity", "weight_pct": 60}, {"class": "gold", "weight_pct": 30}]}
    resp = _client(data_root).put("/plans/alex", json=bad)
    assert resp.status_code == 400
    assert "Target weights must sum to 100%, got 90%" in resp.json()["detail"]
    assert not (data_root / "plans" / "alex.json").exists()


def test_put_rejects_unknown_class_and_other_owner(data_root):
    client = _client(data_root)
    resp = client.put("/plans/alex", json={**PLAN, "target": [{"class": "crypto", "weight_pct": 100}]})
    assert resp.status_code == 400
    assert "target.0.class: Unknown class 'crypto'" in resp.json()["detail"]

    resp = client.put("/plans/alex", json={**PLAN, "owner": "bob"})
    assert resp.status_code == 400
    assert "does not match" in resp.json()["detail"]


def test_unknown_vehicle_ticker_warns_but_saves(data_root, monkeypatch):
    monkeypatch.setattr(plan_mod, "get_instrument_meta", lambda ticker: {})
    resp = _client(data_root).put("/plans/alex", json=PLAN)
    assert resp.status_code == 200
    assert resp.json()["warnings"] == ["GLTL.L (long_gilts) has no instrument metadata"]


def test_corrupt_saved_plan_is_422(data_root):
    (data_root / "plans").mkdir()
    (data_root / "plans" / "alex.json").write_text("{not json")
    resp = _client(data_root).get("/plans/alex")
    assert resp.status_code == 422
    assert "Saved plan for alex is invalid" in resp.json()["detail"]

    bad_sum = {**PLAN, "target": [{"class": "gold", "weight_pct": 90}]}
    (data_root / "plans" / "alex.json").write_text(json.dumps(bad_sum))
    resp = _client(data_root).get("/plans/alex")
    assert resp.status_code == 422
    assert "sum to 100%" in resp.json()["detail"]


def test_unknown_owner_is_rejected(data_root):
    with pytest.raises(OwnerNotFoundError):
        _client(data_root).get("/plans/nobody")


def test_plan_not_readable_by_another_owner(data_root, monkeypatch):
    """With auth on, bob cannot read or write alex's plan (ensure_owner_access)."""
    from backend.auth import get_current_user
    from backend.common import authz

    _client(data_root).put("/plans/alex", json=PLAN)
    monkeypatch.setattr(authz.config, "disable_auth", False, raising=False)
    client = _client(data_root)
    client.app.dependency_overrides[get_current_user] = lambda: "bob"

    with pytest.raises(PermissionDeniedError):
        client.get("/plans/alex")
    with pytest.raises(PermissionDeniedError):
        client.put("/plans/alex", json=PLAN)

    client.app.dependency_overrides[get_current_user] = lambda: "alex"
    assert client.get("/plans/alex").status_code == 200
