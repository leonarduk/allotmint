"""/retirement-readiness/{owner} routes (#10484), on a synthetic returns fixture and plan."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import investment_plan as plan_mod
from backend.common.errors import OwnerNotFoundError, PermissionDeniedError
from backend.retirement import agent, history, readiness
from backend.retirement.long_history import load_long_history
from backend.routes import pension as pension_route
from backend.routes import retirement_readiness as route
from tests.backend.retirement.conftest import FIXTURE

PLAN = {
    "owner": "alex",
    "updated": "2026-10-01",
    "target": [{"class": "cash", "weight_pct": 50}, {"class": "intermediate_gilts", "weight_pct": 50}],
}


@pytest.fixture()
def data_root(monkeypatch, tmp_path):
    accounts = tmp_path / "accounts"
    for owner in ("alex", "bob"):
        (accounts / owner).mkdir(parents=True)
    (accounts / "alex" / "person.json").write_text(json.dumps({"owner": "alex", "dob": "1975-06-15"}))
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(PLAN))
    monkeypatch.setattr(plan_mod.config, "accounts_root", accounts, raising=False)
    monkeypatch.setenv(history.STORE_ENV, str(tmp_path / "store"))
    monkeypatch.setattr(readiness, "load_long_history", lambda: load_long_history(str(FIXTURE)))
    monkeypatch.setattr(readiness, "_latest_gilt_yield", lambda: None)
    monkeypatch.setattr(readiness, "_load_transactions", lambda: [])
    monkeypatch.setattr(agent, "_default_llm", lambda: None)
    monkeypatch.setattr(
        pension_route,
        "build_owner_portfolio",
        lambda owner, **_: {"accounts": [{"account_type": "sipp", "value_estimate_gbp": 80000.0}]},
    )
    return tmp_path


def _client(data_root, raise_server_exceptions=True):
    app = FastAPI()
    app.include_router(route.router)
    app.state.accounts_root = data_root / "accounts"
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_latest_is_404_before_any_run(data_root):
    resp = _client(data_root).get("/retirement-readiness/alex/latest")
    assert resp.status_code == 404
    assert "No retirement readiness report" in resp.json()["detail"]


def test_run_then_latest_and_history(data_root):
    client = _client(data_root)
    resp = client.post(
        "/retirement-readiness/alex/run",
        params={"survival_levels": "95,100", "death_age": 80, "retirement_age": 60, "floor_gbp": 10000},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["headline"]["survival_pct"] == 95.0
    assert report["results"]["simulation"]["floor"]["floor_gbp"] == 10000.0

    latest = client.get("/retirement-readiness/alex/latest")
    assert latest.status_code == 200
    assert latest.json()["run_date"] == report["run_date"]
    assert latest.json()["headline"] == report["headline"]

    trend = client.get("/retirement-readiness/alex/history").json()
    assert trend["owner"] == "alex"
    assert trend["trend"] == [
        {
            "run_date": report["run_date"],
            "survival_pct": 95.0,
            "sustainable_income_gbp": report["headline"]["income_gbp"],
            "pot_gbp": 80000.0,
        }
    ]


def test_history_lists_every_stored_run(data_root):
    history.save_run("alex", {"run_date": "2026-01-01", "headline": {"survival_pct": 95, "income_gbp": 9000}})
    history.save_run("alex", {"run_date": "2026-04-01", "headline": {"survival_pct": 95, "income_gbp": 9500}})
    trend = _client(data_root).get("/retirement-readiness/alex/history").json()["trend"]
    assert [p["sustainable_income_gbp"] for p in trend] == [9000, 9500]


def test_run_without_plan_is_422(data_root):
    (data_root / "plans" / "alex.json").unlink()
    resp = _client(data_root).post("/retirement-readiness/alex/run")
    assert resp.status_code == 422
    assert "no investment plan" in resp.json()["detail"]


def test_bad_survival_levels_is_400(data_root):
    client = _client(data_root)
    assert client.post("/retirement-readiness/alex/run", params={"survival_levels": "x"}).status_code == 400
    assert client.post("/retirement-readiness/alex/run", params={"survival_levels": "150"}).status_code == 400


def test_unknown_owner_is_rejected(data_root):
    # The bare test app has no exception handlers, so the domain error itself is asserted.
    with pytest.raises(OwnerNotFoundError):
        _client(data_root).get("/retirement-readiness/nobody/latest")


def test_owner_access_is_enforced(data_root, monkeypatch):
    def deny(identity, owner, accounts_root=None):
        raise PermissionDeniedError("no")

    monkeypatch.setattr(route, "ensure_owner_access", deny)
    with pytest.raises(PermissionDeniedError):
        _client(data_root).get("/retirement-readiness/alex/history")


def test_routes_do_not_touch_the_plan(data_root):
    before = (data_root / "plans" / "alex.json").read_bytes()
    _client(data_root).post("/retirement-readiness/alex/run", params={"death_age": 80, "retirement_age": 60})
    assert (data_root / "plans" / "alex.json").read_bytes() == before
