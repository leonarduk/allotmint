import json
from contextlib import asynccontextmanager

import httpx
import pytest

from backend.chat import openai_compat_agent
from backend.chat.local_tools import NAVIGATE_TOOL_NAME, ChatPage, LocalTools


class FakeTool:
    def __init__(self, name, description="", input_schema=None):
        self.name = name
        self.description = description
        self.input_schema = input_schema or {"type": "object", "properties": {}}


class FakeToolsResult:
    def __init__(self, tools):
        self.tools = tools


class FakeContentBlock:
    def __init__(self, text):
        self.text = text


class FakeCallToolResult:
    def __init__(self, text, is_error=False):
        self.content = [FakeContentBlock(text)]
        self.is_error = is_error


class FakeSession:
    def __init__(self, tools, tool_results=None):
        self._tools = tools
        self._tool_results = tool_results or {}
        self.calls = []

    async def list_tools(self):
        return FakeToolsResult(self._tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self._tool_results[name]


def _fake_mcp_session_factory(session):
    @asynccontextmanager
    async def _fake_mcp_session(mcp_server_url):
        yield session

    return _fake_mcp_session


def _completion(message):
    return {"choices": [{"message": message}]}


def _tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def _patch_http(monkeypatch, responses):
    """Route httpx.AsyncClient through a MockTransport serving ``responses`` in order."""

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=responses[len(requests) - 1])

    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(openai_compat_agent.httpx, "AsyncClient", client_factory)
    return requests


def test_tool_to_openai_spec_uses_name_as_fallback_description():
    spec = openai_compat_agent._tool_to_openai_spec(FakeTool("list_owners", input_schema={"type": "object"}))
    assert spec == {
        "type": "function",
        "function": {"name": "list_owners", "description": "list_owners", "parameters": {"type": "object"}},
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [('{"a": 1}', {"a": 1}), ({"a": 1}, {"a": 1}), ("", {}), (None, {})],
)
def test_parse_tool_arguments_accepts_string_dict_or_empty(raw, expected):
    assert openai_compat_agent._parse_tool_arguments(raw) == expected


async def test_run_chat_turn_rejects_history_with_consecutive_same_role():
    with pytest.raises(ValueError, match="must alternate"):
        await openai_compat_agent.run_chat_turn(
            "hi",
            [{"role": "user", "content": "earlier"}],
            mcp_server_url="http://localhost:8001/mcp",
            base_url="http://localhost:11434/v1",
            model="m",
        )


async def test_run_chat_turn_returns_direct_answer_and_sends_api_key(monkeypatch):
    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    requests = _patch_http(monkeypatch, [_completion({"role": "assistant", "content": "Hello!"})])

    reply = await openai_compat_agent.run_chat_turn(
        "hi",
        [],
        mcp_server_url="http://localhost:8001/mcp",
        base_url="https://api.deepseek.com/v1/",
        model="deepseek-chat",
        api_key="sk-test",
    )

    assert reply == "Hello!"
    assert str(requests[0].url) == "https://api.deepseek.com/v1/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer sk-test"
    body = json.loads(requests[0].content)
    assert body["model"] == "deepseek-chat"
    assert body["tools"][0]["function"]["name"] == "list_owners"


async def test_run_chat_turn_calls_tool_then_answers(monkeypatch):
    session = FakeSession(
        tools=[FakeTool("get_live_prices")],
        tool_results={"get_live_prices": FakeCallToolResult('{"VOD.L": {"last": 1.0}}')},
    )
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    tool_call = _tool_call("call-1", "get_live_prices", '{"tickers": ["VOD.L"]}')
    requests = _patch_http(
        monkeypatch,
        [
            _completion({"role": "assistant", "content": None, "tool_calls": [tool_call]}),
            _completion({"role": "assistant", "content": "VOD.L is 1.0"}),
        ],
    )

    reply = await openai_compat_agent.run_chat_turn(
        "what is VOD.L trading at?",
        [],
        mcp_server_url="http://localhost:8001/mcp",
        base_url="http://localhost:11434/v1",
        model="qwen3.5:9b",
    )

    assert reply == "VOD.L is 1.0"
    assert session.calls == [("get_live_prices", {"tickers": ["VOD.L"]})]
    assert "Authorization" not in requests[0].headers
    second_messages = json.loads(requests[1].content)["messages"]
    assert second_messages[-2]["tool_calls"] == [tool_call]
    assert second_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"VOD.L": {"last": 1.0}}',
    }


async def test_run_chat_turn_runs_navigate_locally_without_calling_mcp(monkeypatch):
    session = FakeSession(tools=[FakeTool("get_live_prices")])
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    tool_call = _tool_call("call-1", NAVIGATE_TOOL_NAME, '{"path": "/transactions"}')
    requests = _patch_http(
        monkeypatch,
        [
            _completion({"role": "assistant", "content": None, "tool_calls": [tool_call]}),
            _completion({"role": "assistant", "content": "Opening Transactions."}),
        ],
    )
    local = LocalTools(pages=[ChatPage("/transactions", "Transactions")])

    reply = await openai_compat_agent.run_chat_turn(
        "go to transactions",
        [],
        mcp_server_url="http://localhost:8001/mcp",
        base_url="http://localhost:11434/v1",
        model="qwen3.5:9b",
        local_tools=local,
    )

    assert reply == "Opening Transactions."
    assert local.navigate_to == "/transactions"
    assert session.calls == []
    offered = [tool["function"]["name"] for tool in json.loads(requests[0].content)["tools"]]
    assert offered == ["get_live_prices", NAVIGATE_TOOL_NAME]
    assert json.loads(requests[1].content)["messages"][-1]["tool_call_id"] == "call-1"


async def test_run_chat_turn_marks_a_rejected_navigation_as_failed(monkeypatch):
    session = FakeSession(tools=[])
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    tool_call = _tool_call("call-1", NAVIGATE_TOOL_NAME, '{"path": "/admin"}')
    requests = _patch_http(
        monkeypatch,
        [
            _completion({"role": "assistant", "content": None, "tool_calls": [tool_call]}),
            _completion({"role": "assistant", "content": "That page isn't available."}),
        ],
    )
    local = LocalTools(pages=[ChatPage("/transactions", "Transactions")])

    await openai_compat_agent.run_chat_turn(
        "go to admin",
        [],
        mcp_server_url="http://localhost:8001/mcp",
        base_url="http://localhost:11434/v1",
        model="qwen3.5:9b",
        local_tools=local,
    )

    assert local.navigate_to is None
    tool_message = json.loads(requests[1].content)["messages"][-1]
    assert tool_message["content"].startswith("Tool call failed: Unknown page")


async def test_run_chat_turn_reports_failed_tool_call_to_the_model_instead_of_raising(monkeypatch):
    class BoomSession(FakeSession):
        async def call_tool(self, name, arguments):
            raise RuntimeError("MCP server unreachable")

    session = BoomSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    requests = _patch_http(
        monkeypatch,
        [
            _completion(
                {"role": "assistant", "content": "", "tool_calls": [_tool_call("call-1", "list_owners", "{}")]}
            ),
            _completion({"role": "assistant", "content": "I could not list owners."}),
        ],
    )

    reply = await openai_compat_agent.run_chat_turn(
        "who?", [], mcp_server_url="http://localhost:8001/mcp", base_url="http://x/v1", model="m"
    )

    assert reply == "I could not list owners."
    tool_message = json.loads(requests[1].content)["messages"][-1]
    assert tool_message["content"] == "Tool call failed: MCP server unreachable"


async def test_run_chat_turn_raises_when_loop_does_not_converge(monkeypatch):
    session = FakeSession(
        tools=[FakeTool("list_owners")],
        tool_results={"list_owners": FakeCallToolResult("[]")},
    )
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    looping = _completion(
        {"role": "assistant", "content": "", "tool_calls": [_tool_call("call-1", "list_owners", "{}")]}
    )
    _patch_http(monkeypatch, [looping] * openai_compat_agent.MAX_TOOL_ITERATIONS)

    with pytest.raises(RuntimeError, match="did not converge"):
        await openai_compat_agent.run_chat_turn(
            "loop", [], mcp_server_url="http://localhost:8001/mcp", base_url="http://x/v1", model="m"
        )
