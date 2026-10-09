import copy
from contextlib import asynccontextmanager

import pytest

from backend.chat import bedrock_agent
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
        is_error = False

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


async def test_run_chat_turn_runs_navigate_locally_without_calling_mcp(monkeypatch):
    session = FakeSession(tools=[FakeTool("get_live_prices")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))

    responses = [
        _assistant_tool_use("tool-1", NAVIGATE_TOOL_NAME, {"path": "/transactions"}),
        _assistant_text("Opening Transactions."),
    ]
    seen_requests = []

    class FakeBedrock:
        def converse(self, **kwargs):
            # The agent keeps appending to the same messages list; snapshot it.
            seen_requests.append(copy.deepcopy(kwargs))
            return responses[len(seen_requests) - 1]

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())
    local = LocalTools(pages=[ChatPage("/transactions", "Transactions")])

    reply = await bedrock_agent.run_chat_turn(
        "go to transactions",
        [],
        mcp_server_url="https://example.com/mcp",
        bedrock_model_id="amazon.nova-lite-v1:0",
        local_tools=local,
    )

    assert reply == "Opening Transactions."
    assert local.navigate_to == "/transactions"
    assert session.calls == []
    offered = [tool["toolSpec"]["name"] for tool in seen_requests[0]["toolConfig"]["tools"]]
    assert offered == ["get_live_prices", NAVIGATE_TOOL_NAME]
    tool_result = seen_requests[1]["messages"][-1]["content"][0]["toolResult"]
    assert tool_result["status"] == "success"


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


async def test_run_chat_turn_sends_system_prompt_only_when_given(monkeypatch):
    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    seen = []

    class FakeBedrock:
        def converse(self, **kwargs):
            seen.append(kwargs)
            return _assistant_text("ok")

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())
    args = ("hi", [])
    kwargs = {"mcp_server_url": "https://example.com/mcp", "bedrock_model_id": "m"}

    await bedrock_agent.run_chat_turn(*args, **kwargs, system_prompt="on /research/ARG.TO")
    await bedrock_agent.run_chat_turn(*args, **kwargs)

    assert seen[0]["system"] == [{"text": "on /research/ARG.TO"}]
    assert "system" not in seen[1]


def _client_error(code, status=400):
    from botocore.exceptions import ClientError

    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "Converse",
    )


@pytest.fixture
def no_retry_sleep(monkeypatch):
    sleeps = []

    async def _fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(bedrock_agent.asyncio, "sleep", _fake_sleep)
    return sleeps


def _flaky_bedrock(failures, final_response):
    class FlakyBedrock:
        def __init__(self):
            self.seen_messages = []

        def converse(self, **kwargs):
            self.seen_messages.append(copy.deepcopy(kwargs["messages"]))
            if failures:
                raise failures.pop(0)
            return final_response

    return FlakyBedrock()


@pytest.mark.parametrize(
    "error",
    [
        _client_error("ThrottlingException"),
        _client_error("ServiceUnavailableException", 503),
        _client_error("SomeNew5xx", 502),
    ],
)
async def test_run_chat_turn_retries_transient_converse_failure(monkeypatch, no_retry_sleep, error):
    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    fake = _flaky_bedrock([error], _assistant_text("Hello!"))
    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: fake)

    reply = await bedrock_agent.run_chat_turn("hi", [], mcp_server_url="https://example.com/mcp", bedrock_model_id="m")

    assert reply == "Hello!"
    assert len(no_retry_sleep) == 1 and 1.0 <= no_retry_sleep[0] <= 1.5
    # The retry resent exactly the same conversation -- nothing rebuilt or duplicated.
    assert fake.seen_messages[0] == fake.seen_messages[1] == [{"role": "user", "content": [{"text": "hi"}]}]


async def test_run_chat_turn_retries_connection_errors(monkeypatch, no_retry_sleep):
    from botocore.exceptions import EndpointConnectionError

    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    fake = _flaky_bedrock([EndpointConnectionError(endpoint_url="https://bedrock")], _assistant_text("ok"))
    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: fake)

    assert await bedrock_agent.run_chat_turn("hi", [], mcp_server_url="u", bedrock_model_id="m") == "ok"


@pytest.mark.parametrize("error", [_client_error("ValidationException"), _client_error("AccessDeniedException", 403)])
async def test_run_chat_turn_does_not_retry_non_transient_converse_failure(monkeypatch, no_retry_sleep, error):
    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    fake = _flaky_bedrock([error], _assistant_text("unreachable"))
    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: fake)

    with pytest.raises(type(error)) as raised:
        await bedrock_agent.run_chat_turn("hi", [], mcp_server_url="u", bedrock_model_id="m")

    assert raised.value is error
    assert len(fake.seen_messages) == 1
    assert no_retry_sleep == []


async def test_run_chat_turn_gives_up_after_max_converse_retries(monkeypatch, no_retry_sleep, caplog):
    session = FakeSession(tools=[FakeTool("list_owners")])
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    failures = [_client_error("ThrottlingException") for _ in range(10)]
    fake = _flaky_bedrock(failures, _assistant_text("unreachable"))
    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: fake)

    with caplog.at_level("WARNING", logger=bedrock_agent.__name__):
        with pytest.raises(bedrock_agent.ClientError):
            await bedrock_agent.run_chat_turn("hi", [], mcp_server_url="u", bedrock_model_id="m")

    assert len(fake.seen_messages) == bedrock_agent.CONVERSE_MAX_RETRIES + 1
    # Exponential backoff 1s, 2s, 4s, each with up to +50% jitter.
    assert len(no_retry_sleep) == 3
    for delay, base in zip(no_retry_sleep, [1, 2, 4]):
        assert base <= delay <= base * 1.5
    assert sum("failed transiently" in record.message for record in caplog.records) == 3


def test_bedrock_client_disables_botocore_retries(monkeypatch):
    captured = {}
    monkeypatch.setattr(bedrock_agent.boto3, "client", lambda name, config: captured.update(config=config))
    bedrock_agent._bedrock_client.cache_clear()
    try:
        bedrock_agent._bedrock_client()
    finally:
        bedrock_agent._bedrock_client.cache_clear()
    assert captured["config"].retries == {"max_attempts": 1}


async def test_run_chat_turn_limits_restrict_tools_cap_tokens_and_log_calls(monkeypatch):
    """TurnLimits (#10475): only allowed tools offered or run, maxTokens sent, calls and usage recorded."""
    from backend.chat.turn_limits import TurnLimits

    session = FakeSession(
        tools=[FakeTool("get_market_rates"), FakeTool("create_issue")],
        tool_results={"get_market_rates": FakeCallToolResult('{"bank_rate": 2.75}')},
    )
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    first = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "t1", "name": "get_market_rates", "input": {}}},
                    {"toolUse": {"toolUseId": "t2", "name": "create_issue", "input": {"title": "x"}}},
                ],
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 20},
    }
    responses = [first, {**_assistant_text("done"), "usage": {"inputTokens": 50, "outputTokens": 5}}]
    seen = []

    class FakeBedrock:
        def converse(self, **kwargs):
            seen.append(copy.deepcopy(kwargs))
            return responses[len(seen) - 1]

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())
    limits = TurnLimits(allowed_tools={"get_market_rates"}, max_tokens=500)

    reply = await bedrock_agent.run_chat_turn(
        "rates?", [], mcp_server_url="https://example.com/mcp", bedrock_model_id="m", limits=limits
    )

    assert reply == "done"
    assert [t["toolSpec"]["name"] for t in seen[0]["toolConfig"]["tools"]] == ["get_market_rates"]
    assert seen[0]["inferenceConfig"] == {"maxTokens": 500}
    assert session.calls == [("get_market_rates", {})]
    assert [(c["tool"], c["is_error"]) for c in limits.tool_log] == [
        ("get_market_rates", False),
        ("create_issue", True),
    ]
    assert limits.usage == {"input_tokens": 150, "output_tokens": 25}
