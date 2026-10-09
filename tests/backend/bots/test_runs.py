"""Run records and the runner: skipped/failed runs, cadence, idempotency (#10477)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.bots import runner, runs, settings
from backend.bots.registry import BotSettings, RunResult


def test_successful_run_is_recorded(fake_bot):
    record, raw = runner.execute(fake_bot.id, "manual", actor="me")
    assert raw == {"done": True}
    assert record.status == "ok"
    assert record.summary == "did it"
    assert record.duration_seconds is not None
    assert runs.list_runs(fake_bot.id)[0].id == record.id


def test_failed_run_is_recorded_with_full_error(fake_bot):
    def boom(ctx):
        raise RuntimeError("provider down")

    fake_bot.behaviour = boom
    record, raw = runner.execute(fake_bot.id, "schedule")
    assert raw is None
    assert record.status == "failed"
    assert "RuntimeError: provider down" in record.error
    assert "Traceback" in record.error
    assert runs.latest_run(fake_bot.id).status == "failed"


def test_failed_run_reraises_when_asked(fake_bot):
    fake_bot.behaviour = lambda ctx: (_ for _ in ()).throw(ValueError("x"))
    with pytest.raises(ValueError):
        runner.execute(fake_bot.id, "schedule", reraise=True)
    assert runs.latest_run(fake_bot.id).status == "failed"


def test_disabled_bot_records_skipped_scheduled_run(fake_bot):
    settings.save_settings(fake_bot, {"enabled": False})
    record, _ = runner.execute(fake_bot.id, "schedule")
    assert record.status == "skipped"
    assert record.summary == "Disabled in settings"
    assert fake_bot.calls == []


def test_disabled_bot_still_runs_on_direct_invoke(fake_bot):
    settings.save_settings(fake_bot, {"enabled": False})
    record, _ = runner.execute(fake_bot.id, "invoke")
    assert record.status == "ok"


def test_weekly_cadence_skips_until_due(fake_bot):
    settings.save_settings(fake_bot, {"enabled": True, "cadence": "weekly"})
    first, _ = runner.execute(fake_bot.id, "schedule")
    second, _ = runner.execute(fake_bot.id, "schedule")
    assert first.status == "ok"
    assert second.status == "skipped"
    assert "weekly" in second.summary
    assert len(fake_bot.calls) == 1


def test_is_due_rules():
    now = datetime(2026, 10, 9, 1, tzinfo=timezone.utc)
    last = runs.RunRecord(id="x", bot_id="b", trigger="schedule", status="ok", started_at=now - timedelta(days=7))
    assert runner.is_due("daily", last, now)
    assert runner.is_due("weekly", last, now)
    assert not runner.is_due("weekly", last.model_copy(update={"started_at": now - timedelta(days=3)}), now)
    assert runner.is_due("monthly", last.model_copy(update={"started_at": now - timedelta(days=9)}), now)
    assert not runner.is_due("monthly", last.model_copy(update={"started_at": now - timedelta(days=2)}), now)
    assert runner.is_due("weekly", None, now)


def test_next_due_skips_firings_inside_the_cadence_window(fake_bot):
    now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    last = runs.RunRecord(
        id="x", bot_id=fake_bot.id, trigger="schedule", status="ok", started_at=now - timedelta(days=1)
    )
    weekly = BotSettings(cadence="weekly")
    assert runner.next_due(fake_bot.default_schedule, weekly, [last], now) == datetime(
        2026, 10, 15, 3, tzinfo=timezone.utc
    )
    assert runner.next_due(fake_bot.default_schedule, BotSettings(enabled=False), [last], now) is None


def test_start_run_rejects_second_run_while_running(fake_bot):
    first = runner.start_run(fake_bot.id, actor="admin")
    assert first.status == "running"
    with pytest.raises(runner.BotBusyError) as excinfo:
        runner.start_run(fake_bot.id, actor="admin")
    assert excinfo.value.running.id == first.id


def test_scheduled_run_skips_while_manual_run_in_progress(fake_bot):
    runner.start_run(fake_bot.id)
    record, _ = runner.execute(fake_bot.id, "schedule")
    assert record.status == "skipped"
    assert "in progress" in record.summary
    assert fake_bot.calls == []


def test_manual_run_completes_its_own_record(fake_bot):
    started = runner.start_run(fake_bot.id, actor="admin")
    record, _ = runner.execute(fake_bot.id, "manual", run_id=started.id)
    assert record.id == started.id
    assert record.status == "ok"
    assert [r.id for r in runs.list_runs(fake_bot.id)] == [started.id]


def test_stale_running_record_does_not_block(fake_bot):
    stale = runs.RunRecord(
        id="old",
        bot_id=fake_bot.id,
        trigger="manual",
        status="running",
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    runs.save_run(stale)
    assert runner.start_run(fake_bot.id).id != "old"


def test_store_failure_never_stops_the_job(fake_bot, monkeypatch):
    def broken(record):
        raise OSError("disk full")

    monkeypatch.setattr(runner, "save_run", broken)
    record, raw = runner.execute(fake_bot.id, "schedule")
    assert record.status == "ok"
    assert raw == {"done": True}


def test_run_history_is_capped(fake_bot):
    for _ in range(runs.MAX_RUNS + 5):
        runner.execute(fake_bot.id, "manual")
    assert len(runs.list_runs(fake_bot.id)) == runs.MAX_RUNS


def test_ai_usage_fields_are_recorded(fake_bot):
    fake_bot.behaviour = lambda ctx: RunResult(
        status="ok", summary="3 holdings flagged", model="claude-x", tokens_in=100, tokens_out=50, cost_usd=0.01
    )
    record, _ = runner.execute(fake_bot.id, "manual")
    assert (record.model, record.tokens_in, record.tokens_out, record.cost_usd) == ("claude-x", 100, 50, 0.01)


@pytest.mark.parametrize(
    "event,expected",
    [
        ({"source": "aws.events", "detail-type": "Scheduled Event"}, ("schedule", None, None)),
        ({"bot_run_id": "r1", "actor": "a"}, ("manual", "r1", "a")),
        ({}, ("invoke", None, None)),
        (None, ("invoke", None, None)),
    ],
)
def test_trigger_for_event(event, expected):
    assert runner.trigger_for_event(event) == expected


def test_lambda_handler_returns_skip_marker_for_disabled_schedule(fake_bot):
    settings.save_settings(fake_bot, {"enabled": False})
    result = runner.handle_lambda_event(fake_bot.id, {"source": "aws.events"})
    assert result["skipped"] is True
    assert result["reason"] == "Disabled in settings"


def test_dispatch_on_aws_invokes_lambda_async(fake_bot, monkeypatch):
    invoked = {}

    class FakeLambda:
        def invoke(self, **kwargs):
            invoked.update(kwargs)

    import boto3

    monkeypatch.setattr(runner.config, "app_env", "aws")
    monkeypatch.setenv(runner.BOT_LAMBDAS_ENV, '{"fake-bot": "fn-name"}')
    monkeypatch.setattr(boto3, "client", lambda name: FakeLambda())
    record = runner.start_run(fake_bot.id, actor="admin")
    runner.dispatch_run(record, background_tasks=None)
    assert invoked["FunctionName"] == "fn-name"
    assert invoked["InvocationType"] == "Event"
    assert record.id in invoked["Payload"].decode()


def test_dispatch_on_aws_without_lambda_records_failure(fake_bot, monkeypatch):
    monkeypatch.setattr(runner.config, "app_env", "aws")
    monkeypatch.delenv(runner.BOT_LAMBDAS_ENV, raising=False)
    record = runner.dispatch_run(runner.start_run(fake_bot.id), background_tasks=None)
    assert record.status == "failed"
    assert runs.latest_run(fake_bot.id).status == "failed"
