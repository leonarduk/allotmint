import base64

import httpx
import httpx2
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.chat.local_tools import BASE_SYSTEM_PROMPT
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
    assert resp.json()["code"] == "chat_not_configured"


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


def test_post_chat_returns_400_for_malformed_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")

    async def raising_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        raise ValueError("Chat history must alternate user/assistant roles; got consecutive 'user' messages")

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", raising_run_chat_turn)

    resp = client.post(
        "/chat",
        json={"message": "hi", "history": [{"role": "user", "content": "prev"}]},
    )
    # A ValueError from run_chat_turn (malformed conversation, not a server
    # fault) must surface as 400, not an unhandled 500.
    assert resp.status_code == 400


def test_post_chat_returns_502_when_mcp_server_unreachable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "http://localhost:8001/mcp")

    async def raising_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        # The MCP SDK's anyio task group wraps the transport's ConnectError.
        raise ExceptionGroup("unhandled errors in a TaskGroup", [httpx2.ConnectError("All connection attempts failed")])

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", raising_run_chat_turn)

    resp = client.post("/chat", json={"message": "hi"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "mcp_unreachable"
    assert "MCP tools server" in resp.json()["detail"]


def test_post_chat_returns_502_when_llm_provider_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "http://localhost:8001/mcp")
    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")

    async def raising_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        raise httpx.HTTPStatusError("not found", request=request, response=httpx.Response(404, request=request))

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", raising_run_chat_turn)

    resp = client.post("/chat", json={"message": "hi"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "llm_unreachable"
    assert "LLM provider (HTTP 404)" in resp.json()["detail"]


def test_post_chat_returns_502_when_bedrock_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")
    error = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Converse")

    async def raising_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        raise error

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", raising_run_chat_turn)

    resp = client.post("/chat", json={"message": "hi"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "aws_error"
    assert "AWS call failed (AccessDeniedException)" in resp.json()["detail"]


def test_post_chat_finds_upstream_error_via_cause(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "http://localhost:8001/mcp")

    async def raising_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        raise RuntimeError("wrapped") from httpx2.ConnectError("refused")

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", raising_run_chat_turn)

    resp = client.post("/chat", json={"message": "hi"})

    assert resp.status_code == 502
    assert "MCP tools server" in resp.json()["detail"]


def test_post_chat_does_not_mask_unrelated_errors(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "http://localhost:8001/mcp")

    async def raising_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", raising_run_chat_turn)

    with pytest.raises(RuntimeError, match="boom"):
        client.post("/chat", json={"message": "hi"})


def test_post_chat_returns_agent_reply(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")
    captured = {}

    async def fake_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        captured["message"] = message
        captured["history"] = history
        captured["cfg"] = cfg
        captured["mcp_server_url"] = mcp_server_url
        return "hello back"

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", fake_run_chat_turn)

    resp = client.post(
        "/chat",
        json={"message": "hi", "history": [{"role": "user", "content": "prev"}]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "hello back", "navigate_to": None, "files": []}
    assert captured["message"] == "hi"
    assert captured["history"] == [{"role": "user", "content": "prev"}]
    assert captured["mcp_server_url"] == "https://example.com/mcp"
    assert captured["cfg"] is config


def test_post_chat_returns_navigation_requested_by_the_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")

    async def navigating_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        assert [page.path for page in local_tools.pages] == ["/transactions", "/market"]
        local_tools.call("navigate_to_page", {"path": "/transactions"})
        return "Opening Transactions."

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", navigating_run_chat_turn)

    resp = client.post(
        "/chat",
        json={
            "message": "go to the transactions page",
            "pages": [
                {"path": "/transactions", "label": "Transactions"},
                {"path": "/market", "label": "Market"},
            ],
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "Opening Transactions.", "navigate_to": "/transactions", "files": []}


def test_post_chat_returns_files_saved_by_the_model(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")

    async def exporting_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        _, is_error = local_tools.call(
            "export_file",
            {"filename": "audit", "format": "csv", "columns": ["ticker", "days"], "rows": [["VOD.L", 3]]},
        )
        assert not is_error
        return "Your file is ready."

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", exporting_run_chat_turn)

    resp = client.post("/chat", json={"message": "export the audit as csv"})

    assert resp.status_code == 200
    (file,) = resp.json()["files"]
    assert file["filename"] == "audit.csv"
    assert file["media_type"] == "text/csv"
    assert base64.b64decode(file["content_base64"]).decode("utf-8-sig").splitlines() == ["ticker,days", "VOD.L,3"]


@pytest.mark.parametrize("path", ["//evil.example.com", "https://evil.example.com", "transactions"])
def test_post_chat_rejects_off_site_page_paths(client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")

    resp = client.post("/chat", json={"message": "hi", "pages": [{"path": path, "label": "Evil"}]})

    assert resp.status_code == 422


def test_post_chat_passes_page_context_as_system_prompt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")
    captured = {}

    async def fake_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        captured["system_prompt"] = system_prompt
        return "ok"

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", fake_run_chat_turn)

    resp = client.post("/chat", json={"message": "buy?", "context": {"path": "/research/ARG.TO", "ticker": "ARG.TO"}})

    assert resp.status_code == 200
    assert captured["system_prompt"].startswith(BASE_SYSTEM_PROMPT)
    assert "/research/ARG.TO" in captured["system_prompt"]
    assert "ARG.TO" in captured["system_prompt"]


def test_post_chat_without_context_sends_only_the_base_system_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")
    captured = {}

    async def fake_run_chat_turn(message, history, *, cfg, mcp_server_url, local_tools=None, system_prompt=None):
        captured["system_prompt"] = system_prompt
        return "ok"

    monkeypatch.setattr(chat_module, "run_configured_chat_turn", fake_run_chat_turn)

    assert client.post("/chat", json={"message": "hi"}).status_code == 200
    assert captured["system_prompt"] == BASE_SYSTEM_PROMPT


@pytest.mark.parametrize("context", [{"path": "//evil.example"}, {"path": "/research/X", "ticker": "a b;drop"}])
def test_post_chat_rejects_bad_context(client: TestClient, monkeypatch: pytest.MonkeyPatch, context: dict) -> None:
    monkeypatch.setattr(config, "mcp_server_url", "https://example.com/mcp")

    assert client.post("/chat", json={"message": "hi", "context": context}).status_code == 422
