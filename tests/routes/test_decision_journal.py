"""/decision-journal/{owner} routes and the daily run (#10481). Synthetic owner and tickers only."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import investment_plan as plan_mod
from backend.decision_journal import bot
from backend.decision_journal import entries as entries_mod
from backend.decision_journal.capture import ContextTools
from backend.decision_journal.store import load_journal, save_journal
from backend.routes import decision_journal as dj_route
from backend.routes import investment_plan as plan_route
from tests.backend.decision_journal.fixtures import fake_series, sell_entry

PLAN = {
    "owner": "alex",
    "updated": "2026-10-01",
    "target": [{"class": "equity", "weight_pct": 100}],
    "decisions": [{"date": "2025-01-01", "decision": "Start at 100% equity", "alternatives": ["60/40"]}],
}
SELL = {
    "id": "alex:isa:7",
    "owner": "alex",
    "account": "isa",
    "date": date.today().isoformat(),
    "type": "SELL",
    "ticker": "AAA.L",
    "units": 100,
    "price_gbp": 100.0,
}


@pytest.fixture()
def data_root(monkeypatch, tmp_path):
    (tmp_path / "accounts" / "alex").mkdir(parents=True)
    (tmp_path / "accounts" / "alex" / "person.json").write_text(json.dumps({"owner": "alex"}))
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(PLAN))
    monkeypatch.setattr(plan_mod.config, "data_root", tmp_path / "elsewhere", raising=False)
    monkeypatch.setattr(plan_mod, "get_instrument_meta", lambda ticker: {"ticker": ticker})
    monkeypatch.setattr(dj_route, "_owner_transactions", lambda request, owner: [SELL])
    tools = ContextTools({"get_allocation": lambda: {"total_value_gbp": 50_000.0, "values_gbp": {"AAA.L": 5_000.0}}})
    monkeypatch.setattr(dj_route, "default_context_tools", lambda owner, root: tools)
    return tmp_path


def _client(data_root):
    app = FastAPI()
    app.include_router(dj_route.router)
    app.include_router(plan_route.router)
    app.state.accounts_root = data_root / "accounts"
    return TestClient(app)


def _plan_file(data_root):
    return json.loads((data_root / "plans" / "alex.json").read_text(encoding="utf-8"))


def _confirm_body(draft, **overrides):
    body = {**draft, "confirmed": True, "reason": "Owner's own reasoning", "expectation": {"text": "AAA keeps falling"}}
    return {**body, **overrides}


def test_qualifying_sell_is_listed_and_drafted_without_writing(data_root):
    client = _client(data_root)
    before = (data_root / "plans" / "alex.json").read_text()

    listed = client.get("/decision-journal/alex").json()
    assert [c["source_ref"] for c in listed["unlogged"]] == ["alex:isa:7"]
    assert listed["settings"] == {"threshold_gbp": 1000.0}

    draft = client.post("/decision-journal/alex/drafts", json={"source_ref": "alex:isa:7"}).json()
    assert draft["decision"] == "Sold £10,000 of AAA.L"
    assert draft["reason"] == ""
    assert draft["snapshot"]["weights"] == {
        "before_pct": 30.0,
        "after_pct": 10.0,
        "basis": "current holdings; before = current value adjusted by the trade amount",
    }
    # Unconfirmed drafts never reach the plan or the journal.
    assert (data_root / "plans" / "alex.json").read_text() == before
    assert not (data_root / "decision_journal").exists()


def test_confirm_requires_explicit_confirmation_and_owner_reasoning(data_root):
    client = _client(data_root)
    draft = client.post("/decision-journal/alex/drafts", json={"source_ref": "alex:isa:7"}).json()
    for body in (
        {**_confirm_body(draft), "confirmed": False},
        {k: v for k, v in _confirm_body(draft).items() if k != "confirmed"},
        _confirm_body(draft, reason=""),
        _confirm_body(draft, reason="   "),
    ):
        assert client.post("/decision-journal/alex/entries", json=body).status_code == 400
    assert len(_plan_file(data_root)["decisions"]) == 1
    assert not (data_root / "decision_journal").exists()


def test_confirmed_entry_lands_in_plan_and_journal(data_root):
    client = _client(data_root)
    draft = client.post("/decision-journal/alex/drafts", json={"source_ref": "alex:isa:7"}).json()
    resp = client.post("/decision-journal/alex/entries", json=_confirm_body(draft))
    assert resp.status_code == 201, resp.text

    decisions = _plan_file(data_root)["decisions"]
    assert decisions[0] == PLAN["decisions"][0]  # existing decision without an id is untouched
    assert decisions[1] == {
        "id": draft["id"],
        "date": SELL["date"],
        "decision": "Sold £10,000 of AAA.L",
        "alternatives": ["Keep holding AAA.L"],
        "reason": "Owner's own reasoning",
    }
    journal = load_journal("alex", data_root)
    assert journal.entries[0].id == draft["id"]
    assert journal.entries[0].expectation.text == "AAA keeps falling"
    assert len(journal.entries[0].review_due) == 2
    assert client.get("/decision-journal/alex").json()["unlogged"] == []
    # The same draft cannot be logged twice.
    assert client.post("/decision-journal/alex/entries", json=_confirm_body(draft)).status_code == 409


def test_plan_with_decision_ids_round_trips_through_plans_route(data_root):
    client = _client(data_root)
    draft = client.post("/decision-journal/alex/drafts", json={"source_ref": "alex:isa:7"}).json()
    client.post("/decision-journal/alex/entries", json=_confirm_body(draft))
    plan = client.get("/plans/alex").json()["plan"]
    assert client.put("/plans/alex", json=plan).status_code == 200
    assert client.get("/plans/alex").json()["plan"]["decisions"] == plan["decisions"]


def test_plan_without_ids_still_loads_and_bad_ids_are_rejected(data_root):
    client = _client(data_root)
    assert client.get("/plans/alex").status_code == 200
    bad = {**PLAN, "decisions": [{"id": "../x", "date": "2026-01-01", "decision": "x"}]}
    assert client.put("/plans/alex", json=bad).status_code == 400


def test_dismiss_settings_and_plan_change_draft(data_root):
    client = _client(data_root)
    assert client.post("/decision-journal/alex/dismissed", json={"source_ref": "alex:isa:7"}).status_code == 200
    assert client.get("/decision-journal/alex").json()["unlogged"] == []
    assert client.put("/decision-journal/alex/settings", json={"threshold_gbp": -1}).status_code == 422
    assert client.put("/decision-journal/alex/settings", json={"threshold_gbp": 20_000}).status_code == 200
    assert load_journal("alex", data_root).settings.threshold_gbp == 20_000

    draft = client.post(
        "/decision-journal/alex/drafts", json={"previous_target": {"equity": 100}, "target": {"equity": 100}}
    )
    assert draft.status_code == 400
    draft = client.post(
        "/decision-journal/alex/drafts",
        json={"previous_target": {"equity": 100}, "target": {"equity": 60, "long_gilts": 40}},
    ).json()
    assert draft["kind"] == "plan_change" and draft["reason"] == ""


def test_lesson_is_saved_on_an_existing_review_only(data_root):
    journal = load_journal("alex", data_root)
    journal.entries.append(sell_entry())
    bot.run_due_reviews(journal, date(2026, 7, 2), fake_series)
    save_journal(journal, data_root)
    client = _client(data_root)
    url = "/decision-journal/alex/entries/dj-sell-aaa/reviews/{}/lesson"
    assert client.put(url.format(6), json={"lesson": "Owner's note"}).status_code == 200
    assert load_journal("alex", data_root).entries[0].reviews[0].lesson == "Owner's note"
    assert client.put(url.format(12), json={"lesson": "x"}).status_code == 404


def test_daily_run_lists_unlogged_and_runs_due_reviews_without_touching_the_plan(data_root, monkeypatch):
    journal = load_journal("alex", data_root)
    journal.entries.append(sell_entry())
    save_journal(journal, data_root)
    before = (data_root / "plans" / "alex.json").read_text()

    def refuse(*args, **kwargs):
        raise AssertionError("the daily run must never write the plan")

    monkeypatch.setattr(plan_mod, "save_plan", refuse)
    monkeypatch.setattr(entries_mod, "save_plan", refuse)
    sell = {**SELL, "date": "2026-07-01", "id": "alex:isa:9"}
    result = bot.run(as_of=date(2026, 7, 2), data_root=data_root, transactions=[sell], load_series=fake_series)

    assert result["bot"] == "decision_journal" and result["schedule"] == "daily"
    owner = result["owners"]["alex"]
    assert [c["source_ref"] for c in owner["unlogged"]] == ["alex:isa:9"]
    assert owner["reviews_run"] == [{"entry_id": "dj-sell-aaa", "horizon_months": 6}]
    assert (data_root / "plans" / "alex.json").read_text() == before
    assert load_journal("alex", data_root).entries[0].reviews[0].return_basis == "total"
    # A second run the same day has nothing more to do.
    again = bot.run(as_of=date(2026, 7, 2), data_root=data_root, transactions=[], load_series=fake_series)
    assert again["owners"]["alex"]["reviews_run"] == []
