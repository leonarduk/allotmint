from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.support as support


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(support.router)
    return TestClient(app)


def test_post_telegram_happy_path(monkeypatch):
    """POST /support/telegram forwards messages via send_message."""
    sent: dict[str, str] = {}

    def fake_send_message(text: str) -> None:
        sent["text"] = text

    monkeypatch.setattr(support, "send_message", fake_send_message)

    client = make_client()
    resp = client.post("/support/telegram", json={"text": "hi"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert sent["text"] == "hi"


def test_portfolio_health_suggestions(monkeypatch):
    """Regex suggestions are extracted from run_check output."""
    threshold_used: dict[str, float] = {}

    def fake_run_check(threshold: float) -> list[dict]:
        threshold_used["value"] = threshold
        return [
            {"message": "Instrument metadata instruments/FOO.json not found"},
            {"message": "approvals file for 'alice' not found"},
            {"message": "all good"},
        ]

    monkeypatch.setattr(support, "run_check", fake_run_check)

    client = make_client()
    resp = client.post("/support/portfolio-health", json={"threshold": 0.5})
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    findings = data["findings"]
    assert threshold_used["value"] == 0.5

    assert findings[0]["suggestion"] == "Create instruments/FOO.json with instrument details."
    assert findings[1]["suggestion"] == "Add approvals.json under accounts/alice/."
    assert "suggestion" not in findings[2]
