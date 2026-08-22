import json

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
            "checks_skipped": [],
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

    monkeypatch.setattr("backend.routes.trading_agent.publish_alert", fake_publish)
    monkeypatch.setattr("backend.routes.trading_agent.alert_utils.send_push_notification", fake_push)

    client = make_client()
    resp = client.get("/trading-agent/signals", params={"notify_email": "true"})
    assert resp.status_code == 200
    assert published["message"] == "BUY AAA: r"
    assert pushed["message"] == "BUY AAA: r"


def test_notify_email_includes_checks_skipped_suffix(monkeypatch):
    """Route-reconstructed notification messages must include the same
    skipped-checks suffix that trading_agent.run() itself appends, so
    email/push consumers of this endpoint aren't left unaware that
    compliance/screening were bypassed (Codex review on #6798)."""
    fake_signals = [
        {
            "ticker": "AAA",
            "action": "BUY",
            "reason": "r",
            "checks_skipped": ["compliance", "fundamental_screen"],
        }
    ]
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: fake_signals)

    published: dict[str, str] = {}
    pushed: dict[str, str] = {}

    monkeypatch.setattr(
        "backend.routes.trading_agent.publish_alert", lambda alert: published.update(message=alert["message"])
    )
    monkeypatch.setattr(
        "backend.routes.trading_agent.alert_utils.send_push_notification", lambda msg: pushed.update(message=msg)
    )

    client = make_client()
    resp = client.get("/trading-agent/signals", params={"notify_email": "true"})
    assert resp.status_code == 200
    expected = "BUY AAA: r [checks skipped: compliance, fundamental_screen]"
    assert published["message"] == expected
    assert pushed["message"] == expected


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


def test_telegram_send_failure_is_logged_sanitised(monkeypatch, caplog):
    """A Telegram send failure must not crash the endpoint, and the logged
    exception message must have embedded newlines stripped (#5260) --
    redact_token() only strips the bot token, not CRLF characters."""
    fake_signals = [
        {
            "ticker": "AAA",
            "action": "BUY",
            "reason": "r",
        }
    ]
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: fake_signals)

    def boom(text: str) -> None:
        raise RuntimeError("connection failed\nFAKE INJECTED LOG LINE")

    monkeypatch.setattr("backend.routes.trading_agent.send_message", boom)
    monkeypatch.setattr("backend.routes.trading_agent.config.app_env", "local", raising=False)

    client = make_client()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    with caplog.at_level("WARNING", logger="backend.routes.trading_agent"):
        resp = client.get("/trading-agent/signals", params={"notify_telegram": "true"})

    assert resp.status_code == 200
    warning_records = [r for r in caplog.records if "Telegram send failed" in r.message]
    assert len(warning_records) == 1
    assert "\n" not in warning_records[0].message
    assert "connection failed" in warning_records[0].message
    assert "FAKE INJECTED LOG LINE" in warning_records[0].message


def test_no_signals(monkeypatch):
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: [])

    def boom(*_):
        raise AssertionError("should not be called")

    monkeypatch.setattr("backend.routes.trading_agent.publish_alert", boom)
    monkeypatch.setattr("backend.routes.trading_agent.alert_utils.send_push_notification", boom)
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


def test_settings_returns_active_thresholds(monkeypatch):
    client = make_client()
    # Patch after create_app(): reload_config() replaces config.trading_agent
    # with a fresh instance parsed from config.yaml.
    monkeypatch.setattr("backend.routes.trading_agent.config.trading_agent.rsi_buy", 27.5)

    response = client.get("/trading-agent/settings")

    assert response.status_code == 200
    assert response.json() == {
        "rsi_buy": 27.5,
        "rsi_sell": 70.0,
        "rsi_window": 14,
        "ma_short_window": 20,
        "ma_long_window": 50,
        "pe_max": None,
        "de_max": None,
        "min_sharpe": None,
        "max_volatility": None,
    }


def test_settings_uses_effective_strategy_prefs(monkeypatch, tmp_path):
    """strategy_prefs.json overrides must be reflected, matching /signals."""
    (tmp_path / "strategy_prefs.json").write_text(json.dumps({"rsi_buy": 25.0, "pe_max": 12.5}), encoding="utf-8")
    client = make_client()
    monkeypatch.setattr("backend.routes.trading_agent.config.repo_root", tmp_path)

    response = client.get("/trading-agent/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["rsi_buy"] == 25.0
    assert body["pe_max"] == 12.5
    assert body["rsi_sell"] == 70.0


def test_settings_accepts_disabled_rsi_thresholds(monkeypatch):
    """Disabled RSI thresholds (null) must not 500 the settings endpoint."""
    client = make_client()
    monkeypatch.setattr("backend.routes.trading_agent.config.trading_agent.rsi_buy", None)
    monkeypatch.setattr("backend.routes.trading_agent.config.trading_agent.rsi_sell", None)

    response = client.get("/trading-agent/settings")

    assert response.status_code == 200
    assert response.json()["rsi_buy"] is None
    assert response.json()["rsi_sell"] is None
