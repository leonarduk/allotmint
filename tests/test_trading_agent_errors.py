import pandas as pd
import pytest

import pandas as pd

from backend.agent import trading_agent


def test_send_trade_alert_handles_publish_failure(monkeypatch):
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: (_ for _ in ()).throw(RuntimeError("no arn")))
    monkeypatch.setattr(trading_agent.alert_utils, "send_push_notification", lambda msg: None)
    monkeypatch.setattr(trading_agent.config, "telegram_bot_token", None)
    monkeypatch.setattr(trading_agent.config, "telegram_chat_id", None)
    trading_agent.send_trade_alert("msg")


def test_price_column_returns_none():
    df = pd.DataFrame({"open": [1, 2, 3]})
    assert trading_agent._price_column(df) is None


def test_generate_signals_rsi_extremes(monkeypatch):
    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "rsi_buy", None)
    monkeypatch.setattr(cfg, "rsi_sell", None)
    snapshot = {"AAA": {"rsi": 80}, "BBB": {"rsi": 20}}
    signals = trading_agent.generate_signals(snapshot)
    actions = {s["ticker"]: s["action"] for s in signals}
    assert actions == {"AAA": "SELL", "BBB": "BUY"}


def test_alert_on_drawdown_handles_missing_perf(monkeypatch):
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(
        trading_agent,
        "compute_owner_performance",
        lambda owner, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )
    calls = []
    monkeypatch.setattr(trading_agent, "send_trade_alert", lambda msg: calls.append(msg))
    trading_agent._alert_on_drawdown()
    assert calls == []


def test_alert_on_drawdown_emits_alert(monkeypatch):
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(
        trading_agent,
        "compute_owner_performance",
        lambda owner, **kwargs: {"max_drawdown": -0.3},
    )
    calls = []
    monkeypatch.setattr(trading_agent, "send_trade_alert", lambda msg: calls.append(msg))
    trading_agent._alert_on_drawdown(0.2)
    assert len(calls) == 1
