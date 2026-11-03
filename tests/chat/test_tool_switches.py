import copy
import json

import pytest

from backend import config_module
from backend.chat import bedrock_agent, openai_compat_agent, tool_switches
from backend.chat.local_tools import NAVIGATE_TOOL_NAME, ChatPage, LocalTools, merge_tool_lists
from backend.chat.turn_limits import TurnLimits
from tests.chat.test_bedrock_agent import (
    FakeCallToolResult,
    FakeSession,
    FakeTool,
    _assistant_text,
    _assistant_tool_use,
    _fake_mcp_session_factory,
)
from tests.chat.test_openai_compat_agent import _completion, _patch_http, _tool_call


@pytest.fixture
def switches(monkeypatch):
    def set_switches(value):
        monkeypatch.setattr(config_module.config, "mcp_tools", value)

    return set_switches


@pytest.mark.parametrize("value", [None, {}])
def test_every_tool_is_on_by_default(switches, value):
    switches(value)

    assert tool_switches.tool_enabled("get_portfolio") is True


def test_only_an_explicit_false_switches_a_tool_off(switches):
    switches({"get_portfolio": False, "get_account": True})

    assert tool_switches.tool_enabled("get_portfolio") is False
    assert tool_switches.tool_enabled("get_account") is True
    assert tool_switches.tool_enabled("unlisted") is True


@pytest.fixture
def toolsets(monkeypatch):
    def set_toolsets(value):
        monkeypatch.setattr(config_module.config, "mcp_toolsets", value)

    return set_toolsets


def test_an_off_toolset_switches_off_its_tools_even_when_a_tool_says_true(switches, toolsets):
    switches({"create_price_trigger": True})
    toolsets({"triggers": False})

    assert tool_switches.tool_enabled("create_price_trigger") is False
    assert tool_switches.tool_enabled("list_price_triggers") is False
    assert tool_switches.tool_enabled("get_portfolio") is True
    # Local tools belong to no toolset.
    assert tool_switches.tool_enabled(NAVIGATE_TOOL_NAME) is True


def test_an_on_toolset_still_honours_per_tool_switches(switches, toolsets):
    switches({"get_account": False})
    toolsets({"portfolio": True})

    assert tool_switches.tool_enabled("get_account") is False
    assert tool_switches.tool_enabled("get_portfolio") is True


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        # An old key switches the tool it was merged into.
        ({"get_group_portfolio": False}, {"get_portfolio": False}),
        # The new key wins over its old keys.
        ({"get_group_portfolio": False, "get_portfolio": True}, {"get_portfolio": True}),
        # Old keys that disagree: off if any is false.
        ({"get_instrument_metadata": True, "get_instrument_timeseries": False}, {"get_instrument": False}),
        ({"get_instrument_metadata": True, "get_instrument_timeseries": True}, {"get_instrument": True}),
        ({"read_data_file": False}, {"read_data_file": False}),
    ],
)
def test_legacy_tool_names_migrate_with_the_mcp_servers_rules(stored, expected):
    assert tool_switches.migrate_legacy_tool_switches(stored) == expected


def test_tool_enabled_applies_legacy_keys_to_the_merged_tool_and_its_old_name(switches):
    switches({"list_owner_groups": False})

    assert tool_switches.tool_enabled("list_owners") is False
    assert tool_switches.tool_enabled("list_owner_groups") is False


def test_toolset_mirror_covers_every_legacy_target():
    assert set(tool_switches.LEGACY_TOOL_NAMES.values()) <= set(tool_switches.TOOLSET_OF)


def test_merge_tool_lists_drops_switched_off_mcp_and_local_tools(switches):
    switches({"read_data_file": False, NAVIGATE_TOOL_NAME: False})
    local = LocalTools(pages=[ChatPage(path="/research", label="Research")])

    merged = merge_tool_lists([FakeTool("get_portfolio"), FakeTool("read_data_file")], local)

    assert [tool.name for tool in merged] == ["get_portfolio"]


async def test_bedrock_refuses_a_switched_off_tool_without_calling_mcp(monkeypatch, switches):
    switches({"read_data_file": False})
    session = FakeSession(tools=[FakeTool("read_data_file")], tool_results={"read_data_file": FakeCallToolResult("x")})
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    responses = [_assistant_tool_use("t1", "read_data_file", {"path": "a.json"}), _assistant_text("done")]
    sent = []

    class FakeBedrock:
        def converse(self, **kwargs):
            sent.append(copy.deepcopy(kwargs))
            return responses[len(sent) - 1]

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())

    reply = await bedrock_agent.run_chat_turn("read it", [], mcp_server_url="https://x/mcp", bedrock_model_id="m")

    assert reply == "done"
    assert session.calls == []
    assert sent[0]["toolConfig"]["tools"] == []
    result = sent[1]["messages"][-1]["content"][0]["toolResult"]
    assert result["status"] == "error"
    assert "switched off in the admin config" in result["content"][0]["text"]


async def test_openai_compat_refuses_a_switched_off_tool_without_calling_mcp(monkeypatch, switches):
    switches({"read_data_file": False})
    session = FakeSession(tools=[FakeTool("read_data_file")], tool_results={"read_data_file": FakeCallToolResult("x")})
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    requests = _patch_http(
        monkeypatch,
        [
            _completion(
                {"role": "assistant", "content": None, "tool_calls": [_tool_call("c1", "read_data_file", "{}")]}
            ),
            _completion({"role": "assistant", "content": "done"}),
        ],
    )

    reply = await openai_compat_agent.run_chat_turn(
        "read it", [], mcp_server_url="http://localhost:8001/mcp", base_url="http://localhost:11434/v1", model="m"
    )

    assert reply == "done"
    assert session.calls == []
    assert "tools" not in json.loads(requests[0].content) or json.loads(requests[0].content)["tools"] == []
    tool_message = json.loads(requests[1].content)["messages"][-1]
    assert "switched off in the admin config" in tool_message["content"]


async def test_bedrock_allowlist_hides_and_refuses_other_tools(monkeypatch, switches):
    switches({})
    session = FakeSession(
        tools=[FakeTool("get_market_rates"), FakeTool("save_plan")],
        tool_results={"save_plan": FakeCallToolResult("x")},
    )
    monkeypatch.setattr(bedrock_agent, "mcp_session", _fake_mcp_session_factory(session))
    responses = [_assistant_tool_use("t1", "save_plan", {}), _assistant_text("done")]
    sent = []

    class FakeBedrock:
        def converse(self, **kwargs):
            sent.append(copy.deepcopy(kwargs))
            return responses[len(sent) - 1]

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())

    reply = await bedrock_agent.run_chat_turn(
        "go",
        [],
        mcp_server_url="https://x/mcp",
        bedrock_model_id="m",
        limits=TurnLimits(allowed_tools=frozenset({"get_market_rates"})),
    )

    assert reply == "done"
    assert session.calls == []
    assert [t["toolSpec"]["name"] for t in sent[0]["toolConfig"]["tools"]] == ["get_market_rates"]
    result = sent[1]["messages"][-1]["content"][0]["toolResult"]
    assert result["status"] == "error"
    assert "is not available to this agent" in result["content"][0]["text"]


async def test_openai_compat_allowlist_hides_and_refuses_other_tools(monkeypatch, switches):
    switches({})
    session = FakeSession(
        tools=[FakeTool("get_market_rates"), FakeTool("save_plan")],
        tool_results={"save_plan": FakeCallToolResult("x")},
    )
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    requests = _patch_http(
        monkeypatch,
        [
            _completion({"role": "assistant", "content": None, "tool_calls": [_tool_call("c1", "save_plan", "{}")]}),
            _completion({"role": "assistant", "content": "done"}),
        ],
    )

    reply = await openai_compat_agent.run_chat_turn(
        "go",
        [],
        mcp_server_url="http://localhost:8001/mcp",
        base_url="http://localhost:11434/v1",
        model="m",
        limits=TurnLimits(allowed_tools=frozenset({"get_market_rates"})),
    )

    assert reply == "done"
    assert session.calls == []
    assert [t["function"]["name"] for t in json.loads(requests[0].content)["tools"]] == ["get_market_rates"]
    assert "is not available to this agent" in json.loads(requests[1].content)["messages"][-1]["content"]
