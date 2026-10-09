"""POST /plan-brief/{owner}/run and GET /plan-brief/{owner}[/latest|/{id}] (#10475)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common.errors import OwnerNotFoundError, PermissionDeniedError
from backend.plan_brief import service
from backend.plan_brief.agent import READ_ONLY_TOOLS
from backend.routes import plan_brief as route
from tests.backend.plan_brief.conftest import PLAN_DATA, portfolio

MARKET_RATES = {"source": "Bank of England IADB", "latest": {"bank_rate": {"value": 2.75, "date": "2026-10-08"}}}


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 9)


@pytest.fixture()
def data_root(monkeypatch, tmp_path):
    accounts = tmp_path / "accounts"
    for owner in ("alex", "bob"):
        (accounts / owner).mkdir(parents=True)
    (accounts / "alex" / "ISA_transactions.json").write_text(
        json.dumps(
            {
                "account_type": "ISA",
                "transactions": [
                    {"date": "2026-08-02", "type": "BUY", "amount_minor": 100000, "ticker": "VWRL.L"},
                    {"date": "2026-09-18", "type": "DEPOSIT", "amount_minor": 400000},
                ],
            }
        )
    )
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(PLAN_DATA))
    monkeypatch.delenv("PLAN_BRIEFS_URI", raising=False)
    # Only the service's own view of "today" is fixed; datetime itself is untouched.
    monkeypatch.setattr(service, "dt", SimpleNamespace(date=_FixedDate, datetime=datetime, timezone=timezone))
    monkeypatch.setattr(service.portfolio_mod, "build_owner_portfolio", lambda owner, root, **kw: portfolio())
    monkeypatch.setattr(route.config, "mcp_server_url", "http://mcp.test", raising=False)
    return tmp_path


@pytest.fixture()
def mocked_llm(monkeypatch):
    """The provider loop, mocked: one get_market_rates call returning 2.75%, then the reply."""
    calls = []

    async def fake_turn(message, history, *, cfg, mcp_server_url, system_prompt, limits):
        calls.append({"message": message, "allowed": set(limits.allowed_tools)})
        limits.record_call("get_market_rates", {"series": ["bank_rate"]}, json.dumps(MARKET_RATES), False)
        return json.dumps(
            {
                "triggers": [
                    {
                        "trigger": "Bank Rate below 3%",
                        "verdict": "fired",
                        "reason": "Bank Rate is 2.75%.",
                        "evidence": [
                            {
                                "tool": "get_market_rates",
                                "field": "latest.bank_rate.value",
                                "value": 2.75,
                                "source": "Bank of England IADB",
                                "as_of": "2026-10-08",
                            }
                        ],
                    }
                ],
                "prose": "Equity is 6.0pp above target (£6,000). Bank Rate is 2.75%.",
            }
        )

    monkeypatch.setattr("backend.plan_brief.agent.run_configured_chat_turn", fake_turn)
    return calls


def _client(data_root):
    app = FastAPI()
    app.include_router(route.router)
    app.state.accounts_root = data_root / "accounts"
    return TestClient(app)


def test_run_stores_brief_and_latest_returns_it(data_root, mocked_llm):
    client = _client(data_root)
    resp = client.post("/plan-brief/alex/run")
    assert resp.status_code == 200, resp.text
    brief = resp.json()

    rows = {row["class"]: row for row in brief["drift"]["rows"]}
    assert rows["equity"]["drift_pp"] == 6.0 and rows["equity"]["drift_gbp"] == 6000.0
    [trigger] = brief["triggers"]
    assert trigger["verdict"] == "fired"
    assert trigger["evidence"][0]["value"] == 2.75
    assert trigger["evidence"][0]["source"] == "Bank of England IADB"
    assert brief["review"]["due"] is True
    assert brief["cash"][0]["uninvested_since"] == "2026-09-18"
    assert (
        brief["disclaimer"]
        == "Owner's own decisions; attached analysis is historical information, not regulated advice."
    )
    assert brief["as_of"] == "2026-10-09"
    assert (data_root / "plan_briefs" / "alex.json").exists()
    assert mocked_llm[0]["allowed"] == set(READ_ONLY_TOOLS)

    latest = client.get("/plan-brief/alex/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == brief["id"]

    listing = client.get("/plan-brief/alex").json()
    assert listing["briefs"][0] == {
        "id": brief["id"],
        "as_of": "2026-10-09",
        "generated_at": brief["generated_at"],
        "total_value_gbp": 100000.0,
        "out_of_band": ["equity", "long_gilts"],
        "triggers_fired": 1,
        "review_due": True,
    }
    assert client.get(f"/plan-brief/alex/{brief['id']}").json()["id"] == brief["id"]


def test_run_does_not_modify_the_plan(data_root, mocked_llm):
    plan_path = data_root / "plans" / "alex.json"
    before = plan_path.read_bytes()
    _client(data_root).post("/plan-brief/alex/run")
    assert plan_path.read_bytes() == before


def test_second_run_lists_newest_first_and_compares_with_previous(data_root, mocked_llm):
    client = _client(data_root)
    first = client.post("/plan-brief/alex/run").json()
    second = client.post("/plan-brief/alex/run").json()
    assert second["changes"]["previous_brief"] == "2026-10-09"
    assert [b["id"] for b in client.get("/plan-brief/alex").json()["briefs"]] == [second["id"], first["id"]]


def test_latest_is_404_before_any_brief(data_root):
    resp = _client(data_root).get("/plan-brief/alex/latest")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No plan brief saved for alex"


def test_run_without_plan_is_404(data_root, mocked_llm):
    resp = _client(data_root).post("/plan-brief/bob/run")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No investment plan saved for bob"


def test_unknown_brief_id_is_404(data_root):
    assert _client(data_root).get("/plan-brief/alex/nope").status_code == 404


def test_unknown_owner_is_rejected(data_root):
    with pytest.raises(OwnerNotFoundError):
        _client(data_root).get("/plan-brief/nobody/latest")


def test_brief_visible_only_to_its_owner(data_root, mocked_llm, monkeypatch):
    from backend.auth import get_current_user
    from backend.common import authz

    _client(data_root).post("/plan-brief/alex/run")
    monkeypatch.setattr(authz.config, "disable_auth", False, raising=False)
    client = _client(data_root)
    client.app.dependency_overrides[get_current_user] = lambda: "bob"
    for call in (
        lambda: client.get("/plan-brief/alex/latest"),
        lambda: client.get("/plan-brief/alex"),
        lambda: client.post("/plan-brief/alex/run"),
    ):
        with pytest.raises(PermissionDeniedError):
            call()

    client.app.dependency_overrides[get_current_user] = lambda: "alex"
    assert client.get("/plan-brief/alex/latest").status_code == 200
