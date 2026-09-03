import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.routes import chat as chat_module


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_post_chat_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    # disable_auth defaults to True under TESTING (see test_data_quality_admin.py
    # for the same pattern); router registration only applies the auth
    # dependency when it's False, so it must be forced here to exercise that.
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 401


def test_post_chat_returns_503_when_mcp_server_url_unset(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", None)
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 503


def test_post_chat_rejects_invalid_history_role(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")
    resp = client.post(
        "/chat",
        json={"message": "hi", "history": [{"role": "system", "content": "prev"}]},
    )
    # Pydantic validation (Literal["user", "assistant"]) rejects this before
    # it ever reaches run_chat_turn/Bedrock, which would otherwise surface a
    # raw Bedrock 400 to the user for an unsupported message role.
    assert resp.status_code == 422


def test_post_chat_returns_agent_reply(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")
    monkeypatch.setattr(config, "bedrock_model_id", "amazon.nova-lite-v1:0")
    captured = {}

    async def fake_run_chat_turn(message, history, *, mcp_server_url, bedrock_model_id):
        captured["message"] = message
        captured["history"] = history
        captured["mcp_server_url"] = mcp_server_url
        captured["bedrock_model_id"] = bedrock_model_id
        return "hello back"

    monkeypatch.setattr(chat_module, "run_chat_turn", fake_run_chat_turn)

    resp = client.post(
        "/chat",
        json={"message": "hi", "history": [{"role": "user", "content": "prev"}]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "hello back"}
    assert captured["message"] == "hi"
    assert captured["history"] == [{"role": "user", "content": "prev"}]
    assert captured["mcp_server_url"] == "https://example.com/mcp"
    assert captured["bedrock_model_id"] == "amazon.nova-lite-v1:0"
