"""Bot registry, schedules, adapters and settings (#10477)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.agent import trading_agent
from backend.bots import adapters, registry, settings
from backend.bots.registry import BotSettings, Schedule

EXISTING_JOBS = {"trading-agent", "price-refresh", "dividend-refresh", "pension-report"}


def test_existing_jobs_are_registered():
    ids = {bot.id for bot in registry.list_bots()}
    assert EXISTING_JOBS <= ids
    for bot_id in EXISTING_JOBS:
        bot = registry.get_bot(bot_id)
        assert isinstance(bot, registry.Bot)
        assert issubclass(bot.settings_model, BotSettings)


def test_unknown_bot_raises_key_error():
    with pytest.raises(KeyError):
        registry.get_bot("no-such-bot")


@pytest.mark.parametrize("bad_id", ["Upper", "../etc", "", "a" * 70, "has space"])
def test_register_rejects_bad_ids(fake_bot, bad_id):
    fake_bot.id = bad_id
    with pytest.raises(ValueError):
        registry.register_bot(fake_bot, replace=True)


def test_register_rejects_duplicates(fake_bot):
    with pytest.raises(ValueError):
        registry.register_bot(fake_bot)


def test_schedule_descriptions_and_firing_times():
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)  # a Friday
    daily = Schedule(hour=1)
    assert daily.description == "Daily at 01:00 UTC"
    assert next(daily.fire_times_after(now)) == datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)

    weekly = Schedule(hour=7, weekday=0)
    assert weekly.description == "Weekly on Mon at 07:00 UTC"
    assert next(weekly.fire_times_after(now)) == datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)

    monthly = Schedule(hour=7, day=1)
    assert next(monthly.fire_times_after(now)) == datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)


def test_trading_settings_reject_out_of_range_and_inconsistent_values():
    model = adapters.TradingAgentBotSettings
    with pytest.raises(ValidationError):
        model(rsi_buy=150)
    with pytest.raises(ValidationError):
        model(rsi_buy=70, rsi_sell=30)
    with pytest.raises(ValidationError):
        model(ma_short_window=60, ma_long_window=50)
    with pytest.raises(ValidationError):
        model(require_pro_checks=True)  # server policy, not editable


def test_trading_settings_expose_no_secrets():
    schema = adapters.TradingAgentBotSettings.model_json_schema()
    props = set(schema["properties"])
    assert props == {"enabled", "cadence", *adapters.TRADING_THRESHOLD_FIELDS}
    assert not any("key" in p or "token" in p or "secret" in p for p in props)


def test_saved_trading_thresholds_feed_the_next_run():
    bot = registry.get_bot("trading-agent")
    before = trading_agent.load_strategy_config()
    current = settings.load_settings(bot).model_dump()
    settings.save_settings(bot, {**current, "rsi_buy": 25.0, "rsi_sell": 75.0}, actor="admin@example.com")

    cfg = trading_agent.load_strategy_config()
    assert (cfg.rsi_buy, cfg.rsi_sell) == (25.0, 75.0)
    assert cfg.require_pro_checks == before.require_pro_checks


def test_invalid_settings_are_not_saved():
    bot = registry.get_bot("trading-agent")
    with pytest.raises(ValidationError):
        settings.save_settings(bot, {"rsi_buy": -1})
    assert settings.load_stored_settings("trading-agent") == {}


def test_settings_change_is_audited(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.data_quality.audit.append_audit", lambda **kw: calls.append(kw))
    bot = registry.get_bot("price-refresh")
    settings.save_settings(bot, {"enabled": False, "cadence": "daily"}, actor="admin@example.com")
    assert calls and calls[0]["action"] == "bot_settings_update"
    assert calls[0]["before"]["enabled"] is True
    assert calls[0]["after"]["enabled"] is False
    assert calls[0]["actor"] == "admin@example.com"


def test_price_refresh_adapter_reports_empty_refresh_as_failed(monkeypatch):
    from backend.lambda_api import price_refresh

    monkeypatch.setattr(price_refresh, "_run_refresh", lambda: {"tickers": [], "snapshot": {}, "unpriced": []})
    ctx = registry.BotRunContext("r", "price-refresh", "manual", datetime.now(timezone.utc))
    result = registry.get_bot("price-refresh").run(ctx, BotSettings())
    assert result.status == "failed"


def test_price_refresh_adapter_partial_when_some_unpriced(monkeypatch):
    from backend.lambda_api import price_refresh

    monkeypatch.setattr(
        price_refresh, "_run_refresh", lambda: {"tickers": ["A", "B"], "snapshot": {}, "unpriced": ["B"]}
    )
    ctx = registry.BotRunContext("r", "price-refresh", "manual", datetime.now(timezone.utc))
    result = registry.get_bot("price-refresh").run(ctx, BotSettings())
    assert (result.status, result.summary) == ("partial", "1 of 2 tickers priced")


def test_pension_adapter_maps_errors(monkeypatch):
    from backend.lambda_api import pension_report

    monkeypatch.setattr(pension_report, "_run_report", lambda: {"sent": 0, "errors": ["steve: boom"]})
    bot = registry.get_bot("pension-report")
    ctx = registry.BotRunContext("r", bot.id, "manual", datetime.now(timezone.utc) - timedelta(seconds=1))
    result = bot.run(ctx, bot.settings_model())
    assert result.status == "failed"
    assert "steve: boom" in result.error


@pytest.mark.parametrize(
    "cadence,schedule",
    [("weekly", Schedule(hour=7, weekday=0)), ("monthly", Schedule(hour=7, day=1)), ("bogus", Schedule(hour=7, day=1))],
)
def test_pension_schedule_follows_deployed_cadence(monkeypatch, cadence, schedule):
    monkeypatch.setenv(adapters.PENSION_REPORT_CADENCE_ENV, cadence)
    bot = registry.get_bot("pension-report")
    assert bot.default_schedule == schedule
    assert bot.default_settings()["cadence"] == ("weekly" if cadence == "weekly" else "monthly")
