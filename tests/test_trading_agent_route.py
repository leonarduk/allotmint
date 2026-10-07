import logging

from fastapi.testclient import TestClient

import backend.routes.trading_agent as ta
from backend.app import create_app


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
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda **_: fake_signals)
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
            "checks_skipped": [],
        }
    ]


def test_trading_agent_email_error(monkeypatch, caplog):
    fake_signals = [{"ticker": "A", "action": "BUY", "reason": "r"}]
    monkeypatch.setattr(ta.trading_agent, "run", lambda **_: fake_signals)
    monkeypatch.setattr(ta.alert_utils, "send_push_notification", lambda text: None)
    monkeypatch.setattr(ta, "publish_alert", lambda payload: (_ for _ in ()).throw(RuntimeError("nope")))
    with caplog.at_level(logging.INFO):
        result = ta.signals(notify_email=True)
    assert result == [ta.TradingSignal.model_validate(s) for s in fake_signals]
    assert any("SNS topic ARN not configured" in r.message for r in caplog.records)


def test_trading_agent_signals_report_includes_blocked(monkeypatch):
    def fake_run(*, notify, blocked):
        assert notify is False
        blocked.append({"ticker": "BBB", "action": "SELL", "reasons": ["alex: Sold BBB without approval"]})
        return [{"ticker": "AAA", "action": "BUY", "reason": "r"}]

    monkeypatch.setattr(ta.trading_agent, "run", fake_run)
    result = ta.signals_report()
    assert [s.ticker for s in result.signals] == ["AAA"]
    assert result.blocked[0].model_dump() == {
        "ticker": "BBB",
        "action": "SELL",
        "reasons": ["alex: Sold BBB without approval"],
    }
