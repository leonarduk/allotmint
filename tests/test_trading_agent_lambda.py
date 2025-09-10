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
