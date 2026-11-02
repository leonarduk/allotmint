"""The retirement readiness monitor on the Bots page (#10510). Synthetic owners and figures only."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from backend.auth import is_system_job
from backend.bots import registry, runner
from backend.bots.registry import BotRunContext
from backend.bots.runs import RunRecord, list_runs
from backend.common import investment_plan
from backend.lambda_api import retirement_readiness as lambda_handler
from backend.retirement import readiness
from backend.retirement.bot import BOT_ID, RetirementReadinessBot


def _context(owner=None):
    started = datetime(2030, 1, 15, 9, tzinfo=timezone.utc)
    return BotRunContext(run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=started, owner=owner)


def _report(stored=True):
    return {"headline": {"income_gbp": 12345.67}, "storage": {"stored": stored}}


def _run(settings=None, owner=None):
    bot = RetirementReadinessBot()
    return bot.run(_context(owner), settings or bot.settings_model())


def test_registered_as_an_owner_scoped_bot_on_a_quarterly_schedule():
    bot = registry.get_bot(BOT_ID)

    assert isinstance(bot, RetirementReadinessBot)
    assert (bot.kind, bot.scope) == ("ai", "owner")
    assert bot.default_schedule.description == "On day 1 of Jan, Apr, Jul, Oct at 09:00 UTC"
    assert bot.settings_model.model_validate(bot.default_settings()).cadence == "monthly"


def test_quarterly_schedule_fires_on_the_first_of_each_quarter():
    fires = RetirementReadinessBot.default_schedule.fire_times_after(datetime(2030, 1, 15, tzinfo=timezone.utc))

    assert [next(fires) for _ in range(4)] == [
        datetime(2030, month, 1, 9, tzinfo=timezone.utc) for month in (4, 7, 10)
    ] + [datetime(2031, 1, 1, 9, tzinfo=timezone.utc)]


def test_every_quarterly_firing_is_due_and_the_bot_is_overdue_only_after_two_quarters():
    bot = RetirementReadinessBot()
    settings = bot.settings_model.model_validate(bot.default_settings())
    last = RunRecord(
        id="r0", bot_id=BOT_ID, trigger="schedule", status="ok", started_at=datetime(2030, 1, 1, 9, tzinfo=timezone.utc)
    )

    assert runner.next_due(bot.default_schedule, settings, [last], now=last.started_at) == datetime(
        2030, 4, 1, 9, tzinfo=timezone.utc
    )
    assert not runner.is_overdue(bot.default_schedule, settings, [last], now=datetime(2030, 6, 1, tzinfo=timezone.utc))
    assert runner.is_overdue(bot.default_schedule, settings, [last], now=datetime(2030, 7, 10, tzinfo=timezone.utc))


def test_scheduled_lambda_records_a_run_as_a_system_job(monkeypatch):
    seen = []
    monkeypatch.setattr(investment_plan, "plan_owners", lambda data_root=None: {"alex"})

    def fake_run(owner, *, today):
        seen.append((owner, is_system_job()))
        return _report()

    monkeypatch.setattr(readiness, "run", fake_run)

    result = lambda_handler.lambda_handler({"source": "aws.events"}, None)

    assert result == {"status": "ok"}
    assert seen == [("alex", True)]
    record = list_runs(BOT_ID)[0]
    assert (record.trigger, record.status, record.summary) == ("schedule", "ok", "1 report written")


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
    assert result.report == {"owners": 2, "reports": 2, "not_stored": 0, "failed": 0}
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
