from contextlib import asynccontextmanager

import pytest

from backend.chat import bedrock_agent


class FakeTool:
    def __init__(self, name, description="", input_schema=None):
        self.name = name
        self.description = description
        self.inputSchema = input_schema or {"type": "object", "properties": {}}


class FakeToolsResult:
    def __init__(self, tools):
        self.tools = tools


class FakeContentBlock:
    def __init__(self, text):
        self.text = text


class FakeCallToolResult:
    def __init__(self, text, is_error=False):
        self.content = [FakeContentBlock(text)]
        self.isError = is_error


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


def _assistant_text(text):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}}


def _assistant_tool_use(tool_use_id, name, tool_input):
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": tool_use_id, "name": name, "input": tool_input}}],
            }
        }
    }


def test_tool_to_bedrock_spec_uses_name_as_fallback_description():
    tool = FakeTool("list_owners", description="", input_schema={"type": "object"})
    spec = bedrock_agent._tool_to_bedrock_spec(tool)
    assert spec == {
        "toolSpec": {
            "name": "list_owners",
            "description": "list_owners",
            "inputSchema": {"json": {"type": "object"}},
        }
    }


def test_tool_result_to_bedrock_content_joins_text_blocks():
    result = FakeCallToolResult("hello")
    assert bedrock_agent._tool_result_to_bedrock_content(result) == [{"text": "hello"}]


def test_tool_result_to_bedrock_content_preserves_non_text_block():
    class FakeStructuredBlock:
        def model_dump_json(self):
            return '{"type": "structured", "value": 1}'

    class FakeResult:
        content = [FakeStructuredBlock()]
        isError = False

    content = bedrock_agent._tool_result_to_bedrock_content(FakeResult())
    assert content == [{"text": '{"type": "structured", "value": 1}'}]


def test_validate_message_alternation_rejects_consecutive_same_role():
    messages = [
        {"role": "user", "content": [{"text": "a"}]},
        {"role": "user", "content": [{"text": "b"}]},
    ]
    with pytest.raises(ValueError, match="must alternate"):
        bedrock_agent._validate_message_alternation(messages)


def test_validate_message_alternation_accepts_proper_alternation():
    messages = [
        {"role": "user", "content": [{"text": "a"}]},
        {"role": "assistant", "content": [{"text": "b"}]},
        {"role": "user", "content": [{"text": "c"}]},
    ]
    bedrock_agent._validate_message_alternation(messages)  # must not raise


async def test_run_chat_turn_rejects_history_with_consecutive_same_role():
    with pytest.raises(ValueError, match="must alternate"):
        await bedrock_agent.run_chat_turn(
            "hi",
            [{"role": "user", "content": "earlier"}],
            mcp_server_url="https://example.com/mcp",
            bedrock_model_id="amazon.nova-lite-v1:0",
        )


async def test_run_chat_turn_returns_direct_answer_with_no_tool_calls(monkeypatch):
    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))

    class FakeBedrock:
        def converse(self, **kwargs):
            return _assistant_text("Hello!")

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())

    reply = await bedrock_agent.run_chat_turn(
        "hi", [], mcp_server_url="https://example.com/mcp", bedrock_model_id="amazon.nova-lite-v1:0"
    )
    assert reply == "Hello!"


async def test_run_chat_turn_calls_tool_then_answers(monkeypatch):
    session = FakeSession(
        tools=[FakeTool("get_live_prices")],
        tool_results={"get_live_prices": FakeCallToolResult('{"VOD.L": {"last": 1.0}}')},
    )
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))

    responses = [
        _assistant_tool_use("tool-1", "get_live_prices", {"tickers": ["VOD.L"]}),
        _assistant_text("VOD.L is 1.0"),
    ]

    class FakeBedrock:
        def __init__(self):
            self.call_count = 0

        def converse(self, **kwargs):
            response = responses[self.call_count]
            self.call_count += 1
            return response

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())

    reply = await bedrock_agent.run_chat_turn(
        "what's VOD.L trading at?",
        [],
        mcp_server_url="https://example.com/mcp",
        bedrock_model_id="amazon.nova-lite-v1:0",
    )
    assert reply == "VOD.L is 1.0"
    assert session.calls == [("get_live_prices", {"tickers": ["VOD.L"]})]


async def test_run_chat_turn_reports_failed_tool_call_to_the_model_instead_of_raising(monkeypatch):
    class BoomSession(FakeSession):
        async def call_tool(self, name, arguments):
            raise RuntimeError("MCP server unreachable")

    session = BoomSession(tools=[FakeTool("get_live_prices")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))

    responses = [
        _assistant_tool_use("tool-1", "get_live_prices", {"tickers": ["VOD.L"]}),
        _assistant_text("I couldn't fetch that price."),
    ]

    class FakeBedrock:
        def __init__(self):
            self.call_count = 0
            self.seen_messages = []

        def converse(self, **kwargs):
            # Copy: `messages` is the same mutable list across the whole loop,
            # so capturing a bare reference would show later mutations too.
            self.seen_messages.append(list(kwargs["messages"]))
            response = responses[self.call_count]
            self.call_count += 1
            return response

    fake_bedrock = FakeBedrock()
    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: fake_bedrock)

    reply = await bedrock_agent.run_chat_turn(
        "what's VOD.L trading at?",
        [],
        mcp_server_url="https://example.com/mcp",
        bedrock_model_id="amazon.nova-lite-v1:0",
    )
    assert reply == "I couldn't fetch that price."
    # The second converse() call must have seen a toolResult with status "error"
    # describing the failure, not an unhandled exception propagating out.
    last_messages = fake_bedrock.seen_messages[-1]
    tool_result_message = last_messages[-1]
    tool_result = tool_result_message["content"][0]["toolResult"]
    assert tool_result["status"] == "error"
    assert "MCP server unreachable" in tool_result["content"][0]["text"]


async def test_run_chat_turn_raises_after_max_iterations(monkeypatch):
    session = FakeSession(
        tools=[FakeTool("get_live_prices")],
        tool_results={"get_live_prices": FakeCallToolResult("ok")},
    )
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))

    class FakeBedrock:
        def converse(self, **kwargs):
            return _assistant_tool_use("tool-loop", "get_live_prices", {})

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())

    with pytest.raises(RuntimeError, match="did not converge"):
        await bedrock_agent.run_chat_turn(
            "loop forever",
            [],
            mcp_server_url="https://example.com/mcp",
            bedrock_model_id="amazon.nova-lite-v1:0",
        )
