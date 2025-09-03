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
