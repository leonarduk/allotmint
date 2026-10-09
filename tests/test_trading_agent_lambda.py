import pytest

from backend.agent import trading_agent
from backend.bots import runs, settings
from backend.bots.registry import get_bot
from backend.lambda_api import trading_agent as trading_agent_lambda


def test_lambda_handler_calls_run_once(monkeypatch):
    calls = []

    def fake_run():
        calls.append(True)
        return []

    monkeypatch.setattr(trading_agent, "run", fake_run)

    result = trading_agent_lambda.lambda_handler({}, None)

    assert len(calls) == 1
    assert result == {"status": "ok"}


def test_lambda_handler_runs_inside_system_job_context(monkeypatch):
    """The scheduled run has no request user, so it must run as a system job (#8914)."""
    from backend.auth import is_system_job

    seen = []

    def fake_run():
        seen.append(is_system_job())
        return []

    monkeypatch.setattr(trading_agent, "run", fake_run)

    trading_agent_lambda.lambda_handler({}, None)

    assert seen == [True]
    assert is_system_job() is False


def test_lambda_handler_records_the_run(monkeypatch):
    """Every run is recorded for the Bots page (#10477)."""
    monkeypatch.setattr(trading_agent, "run", lambda: [{"ticker": "AAA.L", "action": "BUY", "reason": "rsi"}])

    trading_agent_lambda.lambda_handler({"source": "aws.events"}, None)

    record = runs.latest_run("trading-agent")
    assert (record.trigger, record.status, record.summary) == ("schedule", "ok", "1 signal sent")


def test_lambda_handler_skips_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(trading_agent, "run", lambda: calls.append(True) or [])
    bot = get_bot("trading-agent")
    settings.save_settings(bot, {**settings.load_settings(bot).model_dump(), "enabled": False})

    result = trading_agent_lambda.lambda_handler({"source": "aws.events"}, None)

    assert calls == []
    assert result["status"] == "skipped"
    assert runs.latest_run("trading-agent").status == "skipped"


def test_lambda_handler_records_then_reraises_failures(monkeypatch):
    def boom():
        raise RuntimeError("no prices")

    monkeypatch.setattr(trading_agent, "run", boom)

    with pytest.raises(RuntimeError):
        trading_agent_lambda.lambda_handler({"source": "aws.events"}, None)
    assert runs.latest_run("trading-agent").status == "failed"
