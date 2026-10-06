"""/sleeves/{owner} routes and the sleeved rebalance plan (#9813)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common.errors import PermissionDeniedError
from backend.routes import rebalance as rebalance_route
from backend.routes import sleeves as sleeves_route
from backend.routes import strategies as strategies_route

PORTFOLIO = {
    "accounts": [
        {
            "account_type": "SIPP",
            "_account_stem": "sipp",
            "holdings": [
                {"ticker": "CORE.L", "name": "Core fund", "market_value_gbp": 900.0, "asset_class": "equity"},
                {"ticker": "MOON.L", "name": "Moonshot", "market_value_gbp": 100.0, "asset_class": "equity"},
            ],
        }
    ]
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    accounts = tmp_path / "accounts"
    for owner in ("alex", "bob"):
        (accounts / owner).mkdir(parents=True)
    monkeypatch.setattr(sleeves_route.portfolio_mod, "build_owner_portfolio", lambda *a, **k: PORTFOLIO)
    monkeypatch.setattr(rebalance_route.portfolio_mod, "build_owner_portfolio", lambda *a, **k: PORTFOLIO)
    app = FastAPI()
    for module in (sleeves_route, rebalance_route, strategies_route):
        app.include_router(module.router)
    app.state.accounts_root = accounts
    return TestClient(app)


def _create(client, **body):
    resp = client.post("/sleeves/alex", json={"name": "Speculative", "size_pct": 10, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_listing_has_only_core_by_default(client):
    body = client.get("/sleeves/alex").json()
    assert body["sleeves"] == [
        {"id": "core", "name": "Core", "size_pct": 100.0, "targets": {}, "strategy": None},
    ]
    assert body["assignments"] == {}
    assert body["warnings"] == []
    assert [(h["ticker"], h["value"], h["sleeve_id"]) for h in body["holdings"]] == [
        ("CORE.L", 900.0, "core"),
        ("MOON.L", 100.0, "core"),
    ]


def test_create_assign_and_plan(client):
    client.post("/strategies/alex/100_equity/apply")
    sleeve = _create(client, strategy_id="barbell")
    resp = client.put("/sleeves/alex/assignments/moon.l", json={"sleeve_id": sleeve["id"]})
    assert resp.status_code == 200
    assert resp.json()["assignments"] == {"MOON.L": sleeve["id"]}

    listing = client.get("/sleeves/alex").json()
    assert [s["size_pct"] for s in listing["sleeves"]] == [90.0, 10.0]
    assert listing["sleeves"][0]["strategy"]["id"] == "100_equity"
    assert {h["ticker"]: h["sleeve_id"] for h in listing["holdings"]}["MOON.L"] == sleeve["id"]

    plan = client.get("/rebalance/alex/plan").json()
    assert plan["total_value"] == 900.0
    assert plan["portfolio_total"] == 1000.0
    assert [s["id"] for s in plan["sleeves"]] == ["core", sleeve["id"]]
    assert plan["sleeves"][1]["strategy"]["id"] == "barbell"
    assert plan["sleeves"][1]["plan"]["total_value"] == 100.0

    cash = client.get("/rebalance/alex/new-cash", params={"amount": 100, "account": "sipp", "sleeve": sleeve["id"]})
    assert cash.status_code == 200
    assert {t["asset_class"] for t in cash.json()["trades"]} == {"short_gilts"}


def test_plan_without_sleeves_has_no_sleeve_fields(client):
    client.put("/rebalance/alex/policy", json={"targets": {"equity": 100}})
    plan = client.get("/rebalance/alex/plan").json()
    assert "sleeves" not in plan and "portfolio_total" not in plan


def test_update_apply_delete(client):
    sleeve = _create(client, targets={"equity": 100})
    resp = client.put(f"/sleeves/alex/{sleeve['id']}", json={"size_pct": 20, "name": "Punts"})
    assert resp.status_code == 200 and resp.json()["name"] == "Punts"
    applied = client.post(f"/sleeves/alex/{sleeve['id']}/apply/permanent")
    assert applied.status_code == 200 and applied.json()["strategy"]["id"] == "permanent"
    assert client.post(f"/sleeves/alex/{sleeve['id']}/apply/nope").status_code == 404
    assert client.delete(f"/sleeves/alex/{sleeve['id']}").json() == {"status": "deleted", "id": sleeve["id"]}
    assert len(client.get("/sleeves/alex").json()["sleeves"]) == 1


def test_errors(client, tmp_path):
    assert client.post("/sleeves/alex", json={"name": "S", "size_pct": 10}).status_code == 400
    assert client.put("/sleeves/alex/core", json={"size_pct": 5}).status_code == 403
    assert client.delete("/sleeves/alex/sleeve-missing").status_code == 404
    assert client.put("/sleeves/alex/assignments/MOON.L", json={"sleeve_id": "sleeve-missing"}).status_code == 404
    (tmp_path / "accounts" / "alex" / "settings.json").write_text("{bad")
    assert (
        client.post("/sleeves/alex", json={"name": "S", "size_pct": 10, "targets": {"equity": 100}}).status_code == 409
    )


def test_sleeves_are_owner_scoped(client):
    _create(client, targets={"equity": 100})
    assert len(client.get("/sleeves/bob").json()["sleeves"]) == 1


def test_access_denied(client, monkeypatch):
    def deny(*args, **kwargs):
        raise PermissionDeniedError("nope")

    monkeypatch.setattr(sleeves_route, "ensure_owner_access", deny)
    with pytest.raises(PermissionDeniedError):
        client.get("/sleeves/alex")


def test_tagging_a_ticker_not_held_is_rejected(client):
    sleeve = _create(client, targets={"equity": 100})
    resp = client.put("/sleeves/alex/assignments/TYPO.L", json={"sleeve_id": sleeve["id"]})
    assert resp.status_code == 400
    assert "not one of this owner's holdings" in resp.json()["detail"]
    # Untagging needs no holding, so a stale tag can always be cleared.
    assert client.put("/sleeves/alex/assignments/TYPO.L", json={"sleeve_id": None}).status_code == 200


def test_assignment_response_matches_listing(client):
    sleeve = _create(client, targets={"equity": 100})
    body = client.put("/sleeves/alex/assignments/MOON.L", json={"sleeve_id": sleeve["id"]}).json()
    assert body == client.get("/sleeves/alex").json()
    assert {h["ticker"]: h["sleeve_id"] for h in body["holdings"]}["MOON.L"] == sleeve["id"]
