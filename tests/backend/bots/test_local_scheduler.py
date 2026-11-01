"""Local bot scheduler (#10925): which bots fire here, when, catch-up, and overdue flags."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from backend.bots import local_scheduler, runner, runs
from backend.bots.registry import BotSettings, Schedule, get_bot
from backend.bots.runs import RunRecord
from backend.config import Config

UTC = timezone.utc


def _cfg(app_env="local", bots=None, offline=False) -> Config:
    return Config(app_env=app_env, local_bot_schedule=bots, offline_mode=offline)


def _record(bot_id: str, started: datetime, *, trigger="manual", status="ok") -> RunRecord:
    return runs.save_run(
        RunRecord(id=runs.new_run_id(), bot_id=bot_id, trigger=trigger, status=status, started_at=started)
    )


# ─────────────────────────── which bots fire here ───────────────────────────


def test_local_defaults_to_price_and_dividend_refresh_only():
    assert local_scheduler.local_bot_ids(_cfg()) == {"price-refresh", "dividend-refresh"}
    cfg = _cfg()
    for bot_id in ("trading-agent", "pension-report", "trend-watch", "data-steward"):
        assert not local_scheduler.is_scheduled_here(get_bot(bot_id), cfg)
    assert local_scheduler.is_scheduled_here(get_bot("price-refresh"), cfg)


def test_local_opt_in_and_opt_out():
    cfg = _cfg(bots=["trading-agent"])
    assert local_scheduler.is_scheduled_here(get_bot("trading-agent"), cfg)
    assert not local_scheduler.is_scheduled_here(get_bot("price-refresh"), cfg)
    assert local_scheduler.local_bot_ids(_cfg(bots=[])) == frozenset()


@pytest.mark.parametrize("env", ["aws", "production", None])
def test_deployed_schedules_nothing_itself_but_reports_eventbridge(env):
    cfg = _cfg(app_env=env)
    assert local_scheduler.local_bot_ids(cfg) == frozenset()
    assert local_scheduler.scheduled_bots(cfg) == []
    assert local_scheduler.is_scheduled_here(get_bot("trading-agent"), cfg)


def test_event_driven_bot_is_never_scheduled():
    assert not local_scheduler.is_scheduled_here(get_bot("cash-deployment"), _cfg(bots=["cash-deployment"]))


def test_start_is_a_noop_in_tests_and_lambda(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    assert local_scheduler.start_local_bot_scheduler(_cfg()) is None
    monkeypatch.delenv("TESTING")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "backend")
    assert local_scheduler.start_local_bot_scheduler(_cfg()) is None


def test_start_is_a_noop_off_local(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    assert local_scheduler.start_local_bot_scheduler(_cfg(app_env="aws")) is None
    assert local_scheduler.start_local_bot_scheduler(_cfg(offline=True)) is None


# ──────────────────────────────── timing ────────────────────────────────────


def test_next_firing_groups_bots_due_together(fake_bot):
    other = get_bot("price-refresh")  # 00:00 daily
    when, due = local_scheduler.next_firing([fake_bot, other], datetime(2026, 10, 15, 1, 0, tzinfo=UTC))
    assert when == datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
    assert due == [fake_bot]


def test_previous_firing_weekly():
    sched = Schedule(hour=6, weekday=5)
    # Thursday 2026-10-15 -> previous Saturday 2026-10-10 06:00.
    assert local_scheduler.previous_firing(sched, datetime(2026, 10, 15, 4, 57, tzinfo=UTC)) == datetime(
        2026, 10, 10, 6, 0, tzinfo=UTC
    )


def test_previous_firing_monthly_day_31_spans_short_months():
    sched = Schedule(hour=7, day=31)
    # No 31st in September: the latest firing is 61 days back, on Aug 31.
    assert local_scheduler.previous_firing(sched, datetime(2026, 10, 30, 12, tzinfo=UTC)) == datetime(
        2026, 8, 31, 7, tzinfo=UTC
    )


def test_missed_firing(fake_bot):
    now = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)  # fake bot fires daily at 03:00
    assert local_scheduler.missed_firing(fake_bot, now)  # never run
    _record(fake_bot.id, datetime(2026, 10, 15, 2, 0, tzinfo=UTC))
    assert local_scheduler.missed_firing(fake_bot, now)  # ran before the slot
    _record(fake_bot.id, datetime(2026, 10, 15, 3, 30, tzinfo=UTC), trigger="manual")
    assert not local_scheduler.missed_firing(fake_bot, now)


def test_missed_firing_ignores_disabled_bot(fake_bot, monkeypatch):
    monkeypatch.setattr(local_scheduler, "load_settings", lambda bot: BotSettings(enabled=False))
    assert not local_scheduler.missed_firing(fake_bot, datetime(2026, 10, 15, 4, 0, tzinfo=UTC))


# ───────────────────────────────── loop ─────────────────────────────────────


class _Clock:
    def __init__(self, start: datetime):
        self.now = start
        self.sleeps: List[float] = []

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        if self.now >= datetime(2026, 10, 17, tzinfo=UTC):
            raise asyncio.CancelledError


def _run_loop(cfg, clock, calls) -> None:
    def execute(bot_id, trigger):
        calls.append((bot_id, trigger, clock.now))
        return runner.execute(bot_id, trigger)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(local_scheduler.local_bot_scheduler_loop(cfg, execute=execute, now=clock, sleep=clock.sleep))


def test_loop_catches_up_then_fires_each_slot_once_through_runner(fake_bot):
    _record(fake_bot.id, datetime(2026, 10, 14, 3, 0, tzinfo=UTC), trigger="schedule")
    clock = _Clock(datetime(2026, 10, 15, 4, 0, tzinfo=UTC))
    calls: list = []
    _run_loop(_cfg(bots=[fake_bot.id]), clock, calls)

    assert [(c[0], c[1]) for c in calls] == [(fake_bot.id, "schedule")] * 2
    assert calls[0][2] == datetime(2026, 10, 15, 4, 0, tzinfo=UTC)  # catch-up for the missed 03:00
    assert calls[1][2] == datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
    assert max(clock.sleeps) <= 300  # wakes regularly rather than one long sleep
    recorded = runs.list_runs(fake_bot.id)
    assert [r.trigger for r in recorded[:2]] == ["schedule", "schedule"]
    assert len(fake_bot.calls) == 2


def test_loop_does_not_catch_up_when_slot_already_ran(fake_bot):
    _record(fake_bot.id, datetime(2026, 10, 15, 3, 0, tzinfo=UTC), trigger="schedule")
    clock = _Clock(datetime(2026, 10, 15, 4, 0, tzinfo=UTC))
    calls: list = []
    _run_loop(_cfg(bots=[fake_bot.id]), clock, calls)
    assert [c[2] for c in calls] == [datetime(2026, 10, 16, 3, 0, tzinfo=UTC)]


def test_loop_skips_slots_while_offline(fake_bot):
    _record(fake_bot.id, datetime(2026, 10, 15, 3, 0, tzinfo=UTC), trigger="schedule")
    clock = _Clock(datetime(2026, 10, 15, 4, 0, tzinfo=UTC))
    calls: list = []
    _run_loop(_cfg(bots=[fake_bot.id], offline=True), clock, calls)
    assert calls == []


def test_loop_survives_execute_raising(fake_bot):
    _record(fake_bot.id, datetime(2026, 10, 15, 3, 0, tzinfo=UTC), trigger="schedule")
    clock = _Clock(datetime(2026, 10, 15, 4, 0, tzinfo=UTC))

    def execute(bot_id, trigger):
        raise KeyError(bot_id)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            local_scheduler.local_bot_scheduler_loop(
                _cfg(bots=[fake_bot.id]), execute=execute, now=clock, sleep=clock.sleep
            )
        )
    assert clock.now >= datetime(2026, 10, 17, tzinfo=UTC)


def test_loop_returns_when_nothing_is_scheduled():
    asyncio.run(local_scheduler.local_bot_scheduler_loop(_cfg(bots=[])))


# ──────────────────────────────── overdue ───────────────────────────────────


def test_is_overdue():
    now = datetime(2026, 10, 15, 5, 0, tzinfo=UTC)
    daily = Schedule(hour=0)
    ok = BotSettings()
    recent = [RunRecord(id="a", bot_id="x", trigger="manual", status="ok", started_at=now - timedelta(days=1))]
    old = [RunRecord(id="b", bot_id="x", trigger="manual", status="ok", started_at=now - timedelta(days=5))]
    skipped_only = [RunRecord(id="c", bot_id="x", trigger="schedule", status="skipped", started_at=now)] + old
    assert not runner.is_overdue(daily, ok, recent, now)
    assert runner.is_overdue(daily, ok, old, now)
    assert runner.is_overdue(daily, ok, skipped_only, now)
    assert not runner.is_overdue(daily, ok, [], now)  # never run
    assert not runner.is_overdue(None, ok, old, now)  # not scheduled here
    assert not runner.is_overdue(daily, BotSettings(enabled=False), old, now)
    assert not runner.is_overdue(daily, BotSettings(cadence="weekly"), old, now)
    assert not runner.is_overdue(Schedule(hour=6, weekday=5), ok, old, now)
