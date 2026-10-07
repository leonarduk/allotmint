from backend.lambda_api import trading_agent as trading_agent_lambda


def test_lambda_handler_calls_run_once(monkeypatch):
    calls = []

    def fake_run():
        calls.append(True)

    monkeypatch.setattr(trading_agent_lambda, "run", fake_run)

    result = trading_agent_lambda.lambda_handler({}, None)

    assert len(calls) == 1
    assert result == {"status": "ok"}


def test_lambda_handler_runs_inside_system_job_context(monkeypatch):
    """The scheduled run has no request user, so it must run as a system job (#8914)."""
    from backend.auth import is_system_job

    seen = []
    monkeypatch.setattr(trading_agent_lambda, "run", lambda: seen.append(is_system_job()))

    trading_agent_lambda.lambda_handler({}, None)

    assert seen == [True]
    assert is_system_job() is False
