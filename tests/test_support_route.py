from datetime import datetime

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def test_support_telegram_forwards_message(monkeypatch):
    """POST /support/telegram forwards messages via send_message."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    captured = []
    monkeypatch.setattr("backend.routes.support.send_message", lambda text: captured.append(text))
    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/support/telegram", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert captured == ["hello"]


def test_support_telegram_failure(monkeypatch):
    """send_message failures return HTTP 500."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    def boom(text: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.support.send_message", boom)
    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/support/telegram", json={"text": "fail"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "failed to send message"}


def test_portfolio_health_empty_cache(monkeypatch):
    """POST /support/portfolio-health computes results when no cache is primed."""

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.delenv("DRAWDOWN_THRESHOLD", raising=False)

    from backend.routes import support

    monkeypatch.setattr(support, "_portfolio_health_cache", None)
    monkeypatch.setattr(support, "_portfolio_health_refresh", None)

    calls: list[float] = []

    def fake_run_check(threshold: float) -> list[dict]:
        calls.append(threshold)
        return [{"type": "owner", "message": "Owner foo max drawdown unavailable"}]

    monkeypatch.setattr("backend.routes.support.run_check", fake_run_check)

    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/support/portfolio-health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["findings"] == [
        {"type": "owner", "message": "Owner foo max drawdown unavailable"}
    ]
    generated = datetime.fromisoformat(payload["generated_at"])
    assert isinstance(generated, datetime)
    assert "stale" not in payload
    assert calls == [0.2]
