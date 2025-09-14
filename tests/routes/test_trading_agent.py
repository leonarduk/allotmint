from fastapi.testclient import TestClient

from backend.app import create_app



def make_client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_basic_response_model_validation(monkeypatch):
    fake_signals = [
        {
            "ticker": "AAA",
            "action": "BUY",
            "reason": "r",
            "confidence": 0.9,
            "rationale": "details",
            "ignored": True,
        }
    ]
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: fake_signals)

    client = make_client()
    resp = client.get("/trading-agent/signals")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "ticker": "AAA",
            "action": "BUY",
            "reason": "r",
            "confidence": 0.9,
            "rationale": "details",
        }
    ]


def test_notify_email(monkeypatch):
    fake_signals = [
        {
            "ticker": "AAA",
            "action": "BUY",
            "reason": "r",
        }
    ]
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: fake_signals)

    published: dict[str, str] = {}
    pushed: dict[str, str] = {}

    def fake_publish(alert: dict) -> None:
        published["message"] = alert["message"]

    def fake_push(msg: str) -> None:
        pushed["message"] = msg

    monkeypatch.setattr(
        "backend.routes.trading_agent.publish_alert", fake_publish
    )
    monkeypatch.setattr(
        "backend.routes.trading_agent.alert_utils.send_push_notification", fake_push
    )

    client = make_client()
    resp = client.get("/trading-agent/signals", params={"notify_email": "true"})
    assert resp.status_code == 200
    assert published["message"] == "BUY AAA: r"
    assert pushed["message"] == "BUY AAA: r"


def test_notify_telegram_env_gating(monkeypatch):
    fake_signals = [
        {
            "ticker": "AAA",
            "action": "BUY",
            "reason": "r",
        }
    ]
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: fake_signals)

    sent: dict[str, str] = {}

    def fake_send(text: str) -> None:
        sent["text"] = text

    monkeypatch.setattr("backend.routes.trading_agent.send_message", fake_send)
    monkeypatch.setattr("backend.routes.trading_agent.config.app_env", "local", raising=False)

    client = make_client()

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    resp = client.get("/trading-agent/signals", params={"notify_telegram": "true"})
    assert resp.status_code == 200
    assert "text" not in sent

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    resp = client.get("/trading-agent/signals", params={"notify_telegram": "true"})
    assert resp.status_code == 200
    assert sent["text"] == "BUY AAA: r"


def test_no_signals(monkeypatch):
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: [])

    def boom(*_):
        raise AssertionError("should not be called")

    monkeypatch.setattr(
        "backend.routes.trading_agent.publish_alert", boom
    )
    monkeypatch.setattr(
        "backend.routes.trading_agent.alert_utils.send_push_notification", boom
    )
    monkeypatch.setattr("backend.routes.trading_agent.send_message", boom)

    client = make_client()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    resp = client.get(
        "/trading-agent/signals",
        params={"notify_email": "true", "notify_telegram": "true"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
