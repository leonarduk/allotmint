"""Trend watch on the Bots page: registration, settings and the per-owner run (#10476, #10477)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.bots import registry
from backend.bots.registry import BotRunContext
from backend.bots.settings import save_settings
from backend.lambda_api import trend_watch as lambda_handler
from backend.trend_watch import bot as bot_module
from backend.trend_watch import service
from backend.trend_watch.bot import TrendWatchBot, TrendWatchBotSettings, _run_coroutine
from backend.trend_watch.settings import BOT_ID, load_trend_watch_config


def _context(owner=None):
    return BotRunContext(
        run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=datetime.now(timezone.utc), owner=owner
    )


def test_trend_watch_is_registered_as_a_weekly_owner_scoped_ai_bot():
    bot = registry.get_bot(BOT_ID)

    assert (bot.kind, bot.scope) == ("ai", "owner")
    assert bot.default_schedule.description == "Weekly on Sat at 06:00 UTC"
    assert bot.settings_model.model_validate(bot.default_settings()).cadence == "weekly"


def test_settings_cannot_drop_below_two_agreeing_signals():
    with pytest.raises(ValidationError):
        TrendWatchBotSettings(min_signals=1)


def test_saved_bot_settings_feed_the_next_run():
    save_settings(registry.get_bot(BOT_ID), {"max_investigated": 2, "memory_runs": 6})

    cfg = load_trend_watch_config()

    assert (cfg.max_investigated, cfg.memory_runs) == (2, 6)


def test_run_covers_every_owner_and_records_one_owners_failure(monkeypatch):
    calls = []

    async def fake_run(owner, *, notify):
        calls.append((owner, notify))
        if owner == "joe":
            raise RuntimeError("no prices")
        return {"holdings_checked": 10, "items": [{"ticker": "X"}]}

    monkeypatch.setattr(bot_module, "_owners", lambda context: ["alex", "joe", "lucy"])
    monkeypatch.setattr(service, "run_for_owner", fake_run)

    result = TrendWatchBot().run(_context(), TrendWatchBotSettings())

    assert calls == [("alex", True), ("joe", True), ("lucy", True)]
    assert result.status == "partial"
    assert result.summary.startswith("2 to review of 20 holdings across 2 owners")
    assert result.report["failed"] == [{"owner": "joe", "error": "RuntimeError: no prices"}]
    assert result.report["owners"][0]["report"] == "trend_watch/alex/latest.json"


def test_run_for_a_named_owner_only_and_all_failed_is_failed(monkeypatch):
    async def broken(owner, *, notify):
        raise ValueError("bad")

    monkeypatch.setattr(service, "run_for_owner", broken)

    result = TrendWatchBot().run(_context(owner="alex"), TrendWatchBotSettings())

    assert result.status == "failed"
    assert [f["owner"] for f in result.report["failed"]] == ["alex"]


def test_coroutine_runs_from_inside_an_event_loop():
    async def inner():
        return 42

    async def outer():
        return _run_coroutine(inner())

    assert asyncio.run(outer()) == 42


def test_lambda_goes_through_the_bot_runner(monkeypatch):
    seen = []

    def fake_handle(bot_id, event, *, reraise):
        seen.append((bot_id, event, reraise))
        return {"skipped": True, "reason": "Not due (weekly)"}

    monkeypatch.setattr(lambda_handler, "handle_lambda_event", fake_handle)

    result = lambda_handler.lambda_handler({"source": "aws.events"}, None)

    assert seen == [(BOT_ID, {"source": "aws.events"}, True)]
    assert result == {"status": "skipped", "reason": "Not due (weekly)"}
