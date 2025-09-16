import asyncio
import logging
from dataclasses import dataclass

import pytest


@dataclass
class DummyGoal:
    name: str
    target_amount: float


def test_lambda_handler_suggests_trades(monkeypatch, caplog):
    goal = DummyGoal(name="vacation", target_amount=100.0)

    def fake_load_all_goals():
        return {"alice": [goal]}

    def fake_suggest_trades(actual, target):
        return [{"ticker": "goal", "action": "buy", "amount": 100.0}]

    # Patch both original modules and the task module
    monkeypatch.setattr("backend.common.goals.load_all_goals", fake_load_all_goals)
    monkeypatch.setattr("backend.tasks.auto_rebalance.load_all_goals", fake_load_all_goals)
    monkeypatch.setattr("backend.common.rebalance.suggest_trades", fake_suggest_trades)
    monkeypatch.setattr("backend.tasks.auto_rebalance.suggest_trades", fake_suggest_trades)

    import backend.tasks.auto_rebalance as auto

    with caplog.at_level(logging.INFO):
        result = auto.lambda_handler({}, None)

    assert result == {"status": "ok"}
    assert any(
        "Suggested trades for alice/vacation" in rec.message for rec in caplog.records
    )


def test_schedule_runs_once(monkeypatch):
    import backend.tasks.auto_rebalance as auto

    async def fake_run_once():
        pass

    async def fake_sleep(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(auto, "run_once", fake_run_once)
    monkeypatch.setattr(auto.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(auto.schedule(10))
