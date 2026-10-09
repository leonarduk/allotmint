"""Shared fake bot for the bot registry/runner tests (#10477)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pytest

from backend.bots import registry
from backend.bots.registry import BotRunContext, BotSettings, RunResult, Schedule


class FakeBot:
    id = "fake-bot"
    name = "Fake bot"
    description = "Test double"
    kind = "job"
    scope = "system"
    settings_model = BotSettings
    default_schedule: Optional[Schedule] = Schedule(hour=3)
    timeout_minutes = 30

    def __init__(self) -> None:
        self.calls: List[BotRunContext] = []
        self.behaviour: Callable[[BotRunContext], RunResult] = lambda ctx: RunResult(
            status="ok", summary="did it", raw={"done": True}
        )

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "daily"}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        self.calls.append(context)
        return self.behaviour(context)


@pytest.fixture
def fake_bot():
    bot = FakeBot()
    registry.register_bot(bot, replace=True)
    yield bot
    registry.unregister_bot(bot.id)
