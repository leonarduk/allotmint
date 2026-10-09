"""Cash deployment routes (#10480). Synthetic owner and figures only."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.cash_deployment import bot
from backend.cash_deployment.tranche import ORDER_LIST_LABEL
from backend.common import holding_utils
from backend.common.errors import OwnerNotFoundError
from tests.backend.cash_deployment.fixtures import synthetic_plan, synthetic_portfolio

SCHEDULE = {
    "account": "isa",
    "total_amount_minor": 1_200_000,
    "tranches": 12,
    "cadence": "monthly",
    "start_date": "2026-01-15",
    "target_source": "plan",
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    from backend.routes import cash_deployment as route

    accounts = tmp_path / "accounts"
    owner_dir = accounts / "alex"
    owner_dir.mkdir(parents=True)
    (owner_dir / "isa.json").write_text(json.dumps({"account_type": "ISA", "holdings": []}))
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(synthetic_plan().to_dict()))
    portfolio = synthetic_portfolio()

    def fake_build(owner, root, **kwargs):
        assert kwargs.get("include_account_stem") is True
        return portfolio

    monkeypatch.setattr(bot.portfolio_mod, "build_owner_portfolio", fake_build)
    monkeypatch.setattr(holding_utils, "load_latest_prices", lambda tickers: {"VWX.L": 10.0})
    app = FastAPI()
    app.include_router(route.router)
    app.state.accounts_root = accounts
    return TestClient(app)


def _create(client) -> dict:
    resp = client.post("/cash-deployment/alex/schedules", json=SCHEDULE)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_then_run_drafts_the_first_tranche(client):
    created = _create(client)
    assert created["status"] == "active" and created["id"]

    run = client.get("/cash-deployment/alex", params={"as_of": "2026-01-15"}).json()
    assert run["bot"] == "cash_deployment" and run["status"] == "ok"
    [entry] = run["schedules"]
    assert len(entry["progress"]["tranches"]) == 12
    tranche = entry["tranche"]
    assert tranche["index"] == 0 and tranche["amount_minor"] == 100_000
    assert tranche["label"] == ORDER_LIST_LABEL
    equity = next(o for o in tranche["orders"] if o["asset_class"] == "equity")
    assert equity["ticker"] == "VWX.L" and equity["price_gbp"] == 10.0


def test_run_before_start_has_no_tranche(client):
    _create(client)
    [entry] = client.get("/cash-deployment/alex", params={"as_of": "2026-01-01"}).json()["schedules"]
    assert entry["tranche"] is None
    assert entry["progress"]["tranches"][0]["status"] == "upcoming"


def test_paused_schedule_reports_progress_without_orders(client):
    created = _create(client)
    resp = client.put(f"/cash-deployment/alex/schedules/{created['id']}", json={**SCHEDULE, "status": "paused"})
    assert resp.status_code == 200 and resp.json()["created"] == created["created"]
    run = client.get("/cash-deployment/alex", params={"as_of": "2026-01-15"}).json()
    assert run["status"] == "skipped"
    assert run["schedules"][0]["tranche"] is None
    assert run["schedules"][0]["progress"] is not None


def test_get_one_and_delete(client):
    created = _create(client)
    url = f"/cash-deployment/alex/schedules/{created['id']}"
    assert client.get(url, params={"as_of": "2026-01-15"}).json()["schedule"]["id"] == created["id"]
    assert client.delete(url).json() == {"deleted": created["id"]}
    assert client.get(url).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.get("/cash-deployment/alex").json()["schedules"] == []


def test_rejects_unknown_account_and_bad_input(client):
    assert client.post("/cash-deployment/alex/schedules", json={**SCHEDULE, "account": "gia"}).status_code == 400
    assert client.post("/cash-deployment/alex/schedules", json={**SCHEDULE, "tranches": 0}).status_code == 422
    assert client.post("/cash-deployment/alex/schedules", json={**SCHEDULE, "account": "../x"}).status_code == 422


def test_unknown_owner_raises_owner_not_found(client):
    # The app-level handler turns this into a 404; this bare test app has no handler.
    with pytest.raises(OwnerNotFoundError):
        client.get("/cash-deployment/nobody")


def test_schedule_is_stored_beside_other_settings(client, tmp_path):
    settings = tmp_path / "accounts" / "alex" / "settings.json"
    settings.write_text(json.dumps({"allocation_policy": {"targets": {"equity": 100}, "tolerance_pct": 5}}))
    _create(client)
    data = json.loads(settings.read_text())
    assert data["allocation_policy"]["targets"] == {"equity": 100}
    assert len(data["cash_deployment"]["schedules"]) == 1


def test_unreadable_settings_are_not_overwritten(client, tmp_path):
    settings = tmp_path / "accounts" / "alex" / "settings.json"
    settings.write_text("{not json")
    assert client.post("/cash-deployment/alex/schedules", json=SCHEDULE).status_code == 409
    assert settings.read_text() == "{not json"


def test_malformed_stored_schedule_is_a_conflict_not_a_crash(client, tmp_path):
    created = _create(client)
    settings = tmp_path / "accounts" / "alex" / "settings.json"
    data = json.loads(settings.read_text())
    data["cash_deployment"]["schedules"][0]["tranches"] = "twelve"
    before = json.dumps(data)
    settings.write_text(before)
    url = f"/cash-deployment/alex/schedules/{created['id']}"
    assert client.get("/cash-deployment/alex").status_code == 409
    assert client.get(url).status_code == 409
    assert client.post("/cash-deployment/alex/schedules", json=SCHEDULE).status_code == 409
    assert client.put(url, json=SCHEDULE).status_code == 409
    assert client.delete(url).status_code == 409
    assert settings.read_text() == before


def test_run_is_callable_without_http(tmp_path, monkeypatch):
    """The standalone entry point the #10477 registry will wrap."""
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    monkeypatch.setattr(bot.portfolio_mod, "build_owner_portfolio", lambda *a, **k: synthetic_portfolio())
    result = bot.run("alex", date(2026, 1, 15), accounts_root=tmp_path, prices=lambda tickers: {})
    assert result["status"] == "skipped" and result["schedules"] == []
