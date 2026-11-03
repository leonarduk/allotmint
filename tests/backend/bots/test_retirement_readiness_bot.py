"""The retirement readiness monitor on the Bots page (#10510). Synthetic owners and figures only."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import backend.routes.bots as bots_route
from backend.bots import registry, runs
from backend.bots.digest_models import DigestItem, Severity
from backend.bots.registry import BotRunContext
from backend.common import investment_plan
from backend.common.errors import PermissionDeniedError
from backend.retirement import readiness
from backend.retirement.bot import BOT_ID, RetirementReadinessBot
from tests.backend.routes.test_bots import USER, _client


def _context(owner=None):
    started = datetime(2030, 1, 15, 9, tzinfo=timezone.utc)
    return BotRunContext(run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=started, owner=owner)


def _report(stored=True):
    return {"headline": {"income_gbp": 12345.67}, "storage": {"stored": stored}}


def _run(settings=None, owner=None):
    bot = RetirementReadinessBot()
    return bot.run(_context(owner), settings or bot.settings_model())


def test_registered_as_an_owner_scoped_bot_without_a_schedule():
    bot = registry.get_bot(BOT_ID)

    assert isinstance(bot, RetirementReadinessBot)
    assert (bot.kind, bot.scope) == ("ai", "owner")
    assert bot.default_schedule is None
    assert bot.settings_model.model_validate(bot.default_settings()).cadence == "monthly"


def test_runs_every_owner_with_a_plan_and_keeps_amounts_out_of_the_report(monkeypatch):
    calls = []
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: {"sam", "alex"})

    def fake_run(owner, *, today):
        calls.append((owner, today))
        return _report()

    monkeypatch.setattr(readiness, "run", fake_run)

    result = _run()

    assert calls == [("alex", date(2030, 1, 15)), ("sam", date(2030, 1, 15))]
    assert result.status == "ok"
    assert result.summary == "2 reports written"
    assert result.report == {"owners": 2, "reports": 2, "not_stored": 0, "failed": 0, "digest_items": []}
    assert "12345" not in json.dumps(result.report)


def test_named_owner_runs_alone(monkeypatch):
    calls = []
    monkeypatch.setattr(readiness, "run", lambda owner, *, today: calls.append(owner) or _report())

    assert _run(owner="alex").status == "ok"
    assert calls == ["alex"]


def test_unstored_report_is_partial(monkeypatch):
    monkeypatch.setattr(readiness, "run", lambda owner, *, today: _report(stored=False))

    result = _run(owner="alex")

    assert (result.status, result.summary) == ("partial", "1 report written, 1 not stored")


def test_one_owners_failure_does_not_stop_the_others(monkeypatch):
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: {"alex", "sam"})

    def fake_run(owner, *, today):
        if owner == "sam":
            raise readiness.ReadinessError("no long-history data")
        return _report()

    monkeypatch.setattr(readiness, "run", fake_run)

    result = _run()

    assert result.status == "partial"
    assert result.summary == "1 report written; 1 failed"
    assert result.error == "sam: ReadinessError: no long-history data"


def test_every_owner_failing_is_failed(monkeypatch):
    def boom(owner, *, today):
        raise ValueError("nope")

    monkeypatch.setattr(readiness, "run", boom)

    assert _run(owner="alex").status == "failed"


def test_no_owners_is_skipped(monkeypatch):
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: set())

    result = _run()

    assert (result.status, result.summary) == ("skipped", "No owners with an investment plan")


# ───────────── Digest items (#11312) ─────────────

_CHANGED_REPORT = {
    "headline": {"income_gbp": 12345.67},
    "storage": {"stored": True},
    "assumption_changes": [
        {"input": "fee_pct", "label": "all-in fees", "previous": 0.45, "current": 0.6},
        {"input": "retirement_age", "label": "retirement age", "previous": 65, "current": 67},
    ],
    "market": {"flags": ["UK CPI inflation was 3.8% in 2029, against the 2.5% assumed when converting ..."]},
}


def _digest(result):
    return {item["dedupe_key"]: DigestItem.model_validate(item) for item in result.report["digest_items"]}


def test_changes_and_flags_become_owner_scoped_digest_items_without_figures(monkeypatch):
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: {"alex", "sam"})
    monkeypatch.setattr(readiness, "run", lambda owner, *, today: _CHANGED_REPORT if owner == "alex" else _report())

    result = _run()

    items = _digest(result)
    assert set(items) == {f"{BOT_ID}:alex:assumption_changes", f"{BOT_ID}:alex:inflation_assumption"}
    changes = items[f"{BOT_ID}:alex:assumption_changes"]
    assert (changes.owner, changes.bot, changes.id) == ("alex", BOT_ID, changes.dedupe_key)
    assert (changes.severity, changes.action_required) == (Severity.LOW, False)
    assert changes.title == "Retirement readiness: 2 assumptions changed since the last run"
    assert changes.summary == "Changed: all-in fees, retirement age."
    assert all(item.created == datetime(2030, 1, 15, 9, tzinfo=timezone.utc) for item in items.values())
    text = json.dumps(result.report["digest_items"]).replace(BOT_ID, "")
    for figure in ("12345", "0.45", "0.6", "65", "67", "3.8", "2.5", "£", "%"):
        assert figure not in text, figure


def test_a_run_with_nothing_to_report_adds_no_items(monkeypatch):
    monkeypatch.setattr(readiness, "run", lambda owner, *, today: _report())

    assert _run(owner="alex").report["digest_items"] == []


def test_no_owners_adds_no_items(monkeypatch):
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: set())

    assert _run().report["digest_items"] == []


def test_unstored_report_and_failed_owner_are_owner_items(monkeypatch):
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: {"alex", "sam"})

    def fake_run(owner, *, today):
        if owner == "sam":
            raise readiness.ReadinessError("no plan for sam at /data/sam")
        return _report(stored=False)

    monkeypatch.setattr(readiness, "run", fake_run)

    items = _digest(_run())

    not_stored = items[f"{BOT_ID}:alex:not_stored"]
    failed = items[f"{BOT_ID}:sam:failed"]
    assert (not_stored.owner, not_stored.severity, not_stored.action_required) == ("alex", Severity.MEDIUM, True)
    assert (failed.owner, failed.severity) == ("sam", Severity.MEDIUM)
    # The exception type only: its message can carry paths or figures.
    assert "ReadinessError" in failed.summary and "/data" not in failed.summary


def test_items_are_whole_seconds(monkeypatch):
    monkeypatch.setattr(readiness, "run", lambda owner, *, today: _CHANGED_REPORT)
    started = datetime(2030, 1, 15, 9, 0, 0, 123456, tzinfo=timezone.utc)
    context = BotRunContext(run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=started, owner="alex")

    result = RetirementReadinessBot().run(context, RetirementReadinessBot.settings_model())

    assert {item.created.microsecond for item in _digest(result).values()} == {0}


def test_non_admins_see_only_their_own_owners_items_on_the_runs_api(monkeypatch):
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: {"alex", "sam"})
    monkeypatch.setattr(readiness, "run", lambda owner, *, today: _CHANGED_REPORT)
    result = _run()
    started = datetime(2030, 1, 15, 9, tzinfo=timezone.utc)
    record = runs.RunRecord(
        id="all", bot_id=BOT_ID, trigger="manual", status=result.status, started_at=started, report=result.report
    )
    runs.save_run(record)

    def fake_access(identity, owner, accounts_root=None):
        if owner != "alex":
            raise PermissionDeniedError("no")

    monkeypatch.setattr(bots_route, "ensure_owner_access", fake_access)
    monkeypatch.setattr(bots_route, "is_admin", lambda identity: False)
    client = _client(monkeypatch, identity=USER, disable_auth=False)

    [listed] = client.get(f"/bots/{BOT_ID}/runs").json()
    assert {item["owner"] for item in listed["report"]["digest_items"]} == {"alex"}

    # Every item is owner-scoped (none is system-wide), so access to the owner is what shows it.
    monkeypatch.setattr(bots_route, "ensure_owner_access", lambda identity, owner, accounts_root=None: None)
    [listed] = client.get(f"/bots/{BOT_ID}/runs").json()
    assert {item["owner"] for item in listed["report"]["digest_items"]} == {"alex", "sam"}
