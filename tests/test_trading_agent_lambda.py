import importlib


def test_lambda_handler_calls_run_once(monkeypatch):
    calls = []

    def fake_run():
        calls.append(True)

    monkeypatch.setattr("backend.agent.trading_agent.run", fake_run)
    module = importlib.reload(importlib.import_module("backend.lambda_api.trading_agent"))

    result = module.lambda_handler({}, None)

    assert len(calls) == 1
    assert result == {"status": "ok"}


def test_lambda_handler_runs_inside_system_job_context(monkeypatch):
    """The scheduled run has no request user, so it must run as a system job (#8914)."""
    from backend.auth import is_system_job

    seen = []
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda: seen.append(is_system_job()))
    module = importlib.reload(importlib.import_module("backend.lambda_api.trading_agent"))

    module.lambda_handler({}, None)

    assert seen == [True]
    assert is_system_job() is False
