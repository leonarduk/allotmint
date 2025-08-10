from backend.agent.trading_agent import send_trade_alert


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
