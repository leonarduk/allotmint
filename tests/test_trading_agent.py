import pytest
from backend.common import portfolio_utils

from backend.common import portfolio_utils
from backend.agent.trading_agent import send_trade_alert

# Alias to match the terminology of "generate_signals"
generate_signals = portfolio_utils.check_price_alerts


def test_generate_signals_buy_sell_actions(monkeypatch):
    snapshot = {
        "AAA": {"last_price": 110.0},
        "BBB": {"last_price": 90.0},
    }
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA", "units": 1, "cost_gbp": 100},
                    {"ticker": "BBB", "units": 1, "cost_gbp": 100},
                ]
            }
        ]
    }

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot)
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: [portfolio])
    monkeypatch.setattr("backend.common.alerts.publish_alert", lambda alert: None)

    alerts = generate_signals(threshold_pct=0.05)
    assert len(alerts) == 2
    actions = {a["ticker"]: ("sell" if a["change_pct"] > 0 else "buy") for a in alerts}
    assert actions == {"AAA": "sell", "BBB": "buy"}


def test_generate_signals_emits_alerts(monkeypatch):
    snapshot = {"AAA": {"last_price": 110.0}}
    portfolio = {
        "accounts": [
            {"holdings": [{"ticker": "AAA", "units": 1, "cost_gbp": 100}]}
        ]
    }
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot)
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: [portfolio])

    published = []

    def fake_publish(alert):
        published.append(alert)

    monkeypatch.setattr("backend.common.alerts.publish_alert", fake_publish)

    alerts = generate_signals(threshold_pct=0.05)
    assert alerts == published
    assert published and published[0]["ticker"] == "AAA"


def test_send_trade_alert_sns_only(monkeypatch):
    calls = {"publish": None, "telegram": False}

    def fake_publish(alert):
        calls["publish"] = alert

    def fake_send(msg):
        calls["telegram"] = True

    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", fake_publish)
    monkeypatch.setattr("backend.agent.trading_agent.send_message", fake_send)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    send_trade_alert("hello")

    assert calls["publish"] == {"message": "hello"}
    assert calls["telegram"] is False


def test_send_trade_alert_with_telegram(monkeypatch):
    published = {}
    telegram_msgs = []

    monkeypatch.setattr(
        "backend.agent.trading_agent.publish_alert", lambda alert: published.update(alert)
    )
    monkeypatch.setattr(
        "backend.agent.trading_agent.send_message", lambda msg: telegram_msgs.append(msg)
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")

    send_trade_alert("hi")

    assert published["message"] == "hi"
    assert telegram_msgs == ["hi"]
