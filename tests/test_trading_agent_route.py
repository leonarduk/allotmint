from fastapi.testclient import TestClient

from backend.app import create_app
import backend.routes.trading_agent as ta
import asyncio
import logging
import pytest


def test_trading_agent_signals_route(monkeypatch):
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
    monkeypatch.setattr(
        "backend.agent.trading_agent.run", lambda **_: fake_signals
    )
    app = create_app()
    with TestClient(app) as client:
        token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
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


def test_trading_agent_email_error(monkeypatch, caplog):
    fake_signals = [{"ticker": "A", "action": "BUY", "reason": "r"}]
    monkeypatch.setattr(ta.trading_agent, "run", lambda **_: fake_signals)
    monkeypatch.setattr(ta.alert_utils, "send_push_notification", lambda text: None)
    monkeypatch.setattr(ta, "publish_alert", lambda payload: (_ for _ in ()).throw(RuntimeError("nope")))
    with caplog.at_level(logging.INFO):
        result = asyncio.run(ta.signals(notify_email=True))
    assert result == [ta.TradingSignal.model_validate(s) for s in fake_signals]
    assert any("SNS topic ARN not configured" in r.message for r in caplog.records)
