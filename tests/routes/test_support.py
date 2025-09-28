from datetime import timedelta

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


def test_portfolio_health_handles_run_check_errors(monkeypatch):
    """Failures during recompute return cached data with an error status."""

    monkeypatch.setattr(support, "_portfolio_health_cache", None)
    monkeypatch.setattr(support, "_portfolio_health_refresh", None)

    call_state = {"count": 0}

    def fake_run_check(threshold: float) -> list[dict]:
        call_state["count"] += 1
        if call_state["count"] == 1:
            return [{"message": "initial"}]
        raise RuntimeError("boom")

    monkeypatch.setattr(support, "run_check", fake_run_check)

    client = make_client()

    # Prime the cache with a successful response.
    first_resp = client.post("/support/portfolio-health", json={"threshold": 0.3})
    assert first_resp.status_code == 200
    cached_payload = first_resp.json()
    assert cached_payload["status"] == "ok"

    # Mark the cache as stale so the next request triggers a refresh attempt.
    assert support._portfolio_health_cache is not None
    support._portfolio_health_cache.generated_at = (
        support._now() - support._portfolio_health_ttl - timedelta(seconds=1)
    )
    stale_generated_at = support._portfolio_health_cache.generated_at.isoformat()

    # First retry kicks off the failing background task.
    retry_resp = client.post("/support/portfolio-health", json={"threshold": 0.3})
    assert retry_resp.status_code == 200

    # A subsequent call should observe the failed task and surface the cached data.
    final_resp = client.post("/support/portfolio-health", json={"threshold": 0.3})
    assert final_resp.status_code == 200
    data = final_resp.json()
    assert data["status"] == "error"
    assert data["stale"] is True
    assert data["findings"] == cached_payload["findings"]
    assert data["generated_at"] == stale_generated_at


def test_portfolio_health_initial_failure_returns_error(monkeypatch):
    """Initial computation failures return a structured error payload."""

    monkeypatch.setattr(support, "_portfolio_health_cache", None)
    monkeypatch.setattr(support, "_portfolio_health_refresh", None)

    def boom(threshold: float) -> list[dict]:  # pragma: no cover - signature for typing
        raise RuntimeError("boom")

    monkeypatch.setattr(support, "run_check", boom)

    client = make_client()
    resp = client.post("/support/portfolio-health", json={"threshold": 0.1})

    assert resp.status_code == 200
    assert resp.json() == {"status": "error", "stale": True}
