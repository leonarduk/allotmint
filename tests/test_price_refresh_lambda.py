import importlib
import sys
from types import SimpleNamespace

import backend.common.prices as prices


def _import_lambda(monkeypatch, env_value):
    sentinel = object()
    monkeypatch.setattr(prices, "refresh_prices", lambda: sentinel)
    monkeypatch.setenv("ALLOTMINT_ENABLE_TRADING_AGENT", env_value)

    sys.modules.pop("backend.lambda_api.price_refresh", None)
    mod = importlib.import_module("backend.lambda_api.price_refresh")

    agent_state = SimpleNamespace(called=False)

    def fake_run():
        agent_state.called = True

    monkeypatch.setattr(mod, "trading_agent", SimpleNamespace(run=fake_run))

    return mod, agent_state, sentinel


def test_run_called_when_enabled(monkeypatch):
    mod, agent, sentinel = _import_lambda(monkeypatch, "true")
    result = mod.lambda_handler({}, {})
    assert agent.called is True
    assert result is sentinel


def test_run_not_called_when_disabled(monkeypatch):
    mod, agent, sentinel = _import_lambda(monkeypatch, "false")
    result = mod.lambda_handler({}, {})
    assert agent.called is False
    assert result is sentinel
