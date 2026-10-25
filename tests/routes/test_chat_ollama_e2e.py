"""End-to-end coverage of ``CHAT_PROVIDER=ollama`` through ``POST /chat`` (#7879).

The unit tests mock each layer separately (``tests/chat/test_providers.py``,
``tests/chat/test_openai_compat_agent.py``). These tests only stub the two
network edges -- the MCP tools session and the OpenAI-compatible HTTP
transport -- so a regression in route wiring, provider resolution or the
request shape sent to Ollama fails here.
"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.chat import bedrock_agent, openai_compat_agent
from backend.config import config

PAGES = [
    {"path": "/transactions", "label": "Transactions"},
    {"path": "/market", "label": "Market"},
]


class _NoToolsMcpSession:
    async def list_tools(self):
        return SimpleNamespace(tools=[])

    async def call_tool(self, name, arguments):
        raise AssertionError(f"unexpected MCP tool call {name}")


@asynccontextmanager
async def _fake_mcp_session(mcp_server_url):
    yield _NoToolsMcpSession()


@pytest.fixture
def ollama_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # create_app() reloads config, so patch it afterwards.
    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    monkeypatch.setattr(config, "mcp_server_url", "http://localhost:8001/mcp")
    monkeypatch.setattr(config, "chat_provider", "ollama")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "chat_base_url", None)
    monkeypatch.setattr(config, "chat_model", None)
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session)

    async def bedrock_must_not_run(*args, **kwargs):
        raise AssertionError("CHAT_PROVIDER=ollama must not reach Bedrock")

    monkeypatch.setattr(bedrock_agent, "run_chat_turn", bedrock_must_not_run)
    return client


def _patch_ollama_transport(monkeypatch: pytest.MonkeyPatch, messages: list) -> list:
    """Serve ``messages`` as successive chat-completion replies; return the requests seen."""

    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": messages[len(requests) - 1]}]})

    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(openai_compat_agent.httpx, "AsyncClient", client_factory)
    return requests


def test_ollama_reply_flows_through_the_chat_route(ollama_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _patch_ollama_transport(monkeypatch, [{"role": "assistant", "content": "hello from ollama"}])

    resp = ollama_client.post("/chat", json={"message": "hi"})

    assert resp.status_code == 200
    assert resp.json() == {"reply": "hello from ollama", "navigate_to": None, "files": []}
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://localhost:11434/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body["model"] == "qwen3.5:9b"
    assert body["messages"][-1] == {"role": "user", "content": "hi"}


def test_ollama_tool_call_round_trip_through_the_chat_route(
    ollama_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "navigate_to_page", "arguments": json.dumps({"path": "/transactions"})},
    }
    requests = _patch_ollama_transport(
        monkeypatch,
        [
            {"role": "assistant", "content": "", "tool_calls": [tool_call]},
            {"role": "assistant", "content": "Opening Transactions."},
        ],
    )

    resp = ollama_client.post("/chat", json={"message": "go to transactions", "pages": PAGES})

    assert resp.status_code == 200
    assert resp.json() == {"reply": "Opening Transactions.", "navigate_to": "/transactions", "files": []}
    assert len(requests) == 2
    offered = {tool["function"]["name"] for tool in json.loads(requests[0].content)["tools"]}
    assert "navigate_to_page" in offered
    second_messages = json.loads(requests[1].content)["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call-1"
