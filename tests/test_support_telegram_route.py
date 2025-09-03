import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.support as support_module


def create_client() -> TestClient:
    app = FastAPI()
    app.include_router(support_module.router)
    return TestClient(app)


def test_post_telegram_success(monkeypatch):
    sent = {}

    def fake_send_message(text: str) -> None:
        sent["text"] = text

    monkeypatch.setattr("backend.utils.telegram_utils.send_message", fake_send_message)
    # reload to ensure router uses the patched function
    global support_module
    support_module = importlib.reload(support_module)

    client = create_client()
    resp = client.post("/support/telegram", json={"text": "hi"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert sent["text"] == "hi"


def test_post_telegram_handles_error(monkeypatch):
    def fake_send_message(_text: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.utils.telegram_utils.send_message", fake_send_message)
    global support_module
    support_module = importlib.reload(support_module)

    client = create_client()
    resp = client.post("/support/telegram", json={"text": "hi"})

    assert resp.status_code == 500
    assert resp.json()["detail"] == "failed to send message"
