"""Context summary for decision drafts (#10487): read-only allowlist, facts only, mocked models only."""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from backend.chat import bedrock_agent, openai_compat_agent, providers
from backend.decision_journal import summary
from backend.decision_journal.capture import READ_ONLY_CONTEXT_TOOLS

MCP_URL = "https://mcp.example.test/mcp"
CFG = SimpleNamespace(mcp_server_url=MCP_URL)
# A synthetic MCP toolset: two allowlisted reads plus write tools and other reads capture must not see.
MCP_TOOLSET = [
    "get_live_prices",
    "get_allocation",
    "get_portfolio",
    "save_investment_plan",
    "add_transaction",
    "create_github_issue",
]
SNAPSHOT = {
    "taken_on": "2026-10-09",
    "instrument": "AAA.L",
    "trade_type": "SELL",
    "trade_date": "2026-10-01",
    "amount_gbp": 10_000.0,
    "weights": {"before_pct": 30.0, "after_pct": 20.0},
    "technicals": {"return_3m_pct": -4.0, "return_12m_pct": 11.5},
    "valuation": {"pe_ratio": 14.2},
}
GOOD_REPLY = (
    "On 2026-10-01 £10,000 of AAA.L was sold, taking its weight from 30.0% to 20.0% of the portfolio. "
    "It had returned -4.0% over three months and 11.5% over twelve, on a P/E of 14.2."
)
DRAFT = {"id": "dj-0123456789ab", "kind": "trade", "reason": "", "decision": "Sold £10,000 of AAA.L"}


class FakeTurn:
    def __init__(self, reply="", error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def __call__(self, message, history, **kwargs):
        self.calls.append({"message": message, "history": history, **kwargs})
        if self.error is not None:
            raise self.error
        return self.reply


def _summarise(reply="", error=None, snapshot=SNAPSHOT):
    turn = FakeTurn(reply, error)
    return summary.summarise_context(snapshot, chat_turn=turn, cfg=CFG), turn


def test_summary_is_asked_for_with_only_the_read_only_allowlist():
    (text, note), turn = _summarise(GOOD_REPLY)

    assert (text, note) == (GOOD_REPLY, None)
    [call] = turn.calls
    limits = call["limits"]
    assert limits.allowed_tools == READ_ONLY_CONTEXT_TOOLS
    assert limits.max_iterations == summary.MAX_TOOL_CALL_ROUNDS
    assert limits.max_tokens == summary.MAX_OUTPUT_TOKENS
    assert call["system_prompt"] == summary.SYSTEM_PROMPT
    assert call["mcp_server_url"] == MCP_URL and call["history"] == []
    for name in MCP_TOOLSET:
        assert limits.allows(name) == (name in READ_ONLY_CONTEXT_TOOLS), name
    assert json.loads(call["message"].split("\n", 2)[2]) == SNAPSHOT


def test_add_context_summary_stores_it_in_the_snapshot_and_leaves_reason_blank():
    turn = FakeTurn(GOOD_REPLY)
    draft = summary.add_context_summary(
        {**DRAFT, "snapshot": {**SNAPSHOT, "summary_note": "stale"}}, chat_turn=turn, cfg=CFG
    )

    assert draft["snapshot"]["summary"] == GOOD_REPLY
    assert "summary_note" not in draft["snapshot"]
    assert draft["reason"] == ""
    assert "summary_note" not in turn.calls[0]["message"]  # earlier summary fields are not facts


def test_not_configured_returns_the_draft_without_a_summary_and_says_why():
    turn = FakeTurn(GOOD_REPLY)
    draft = summary.add_context_summary(
        {**DRAFT, "snapshot": dict(SNAPSHOT)}, chat_turn=turn, cfg=SimpleNamespace(mcp_server_url=None)
    )

    assert "summary" not in draft["snapshot"]
    assert draft["snapshot"]["summary_note"] == summary.NOTE_NOT_CONFIGURED
    assert turn.calls == []


def test_provider_failure_does_not_block_drafting(caplog):
    with caplog.at_level("WARNING", logger=summary.__name__):
        (text, note), _ = _summarise(error=httpx.ConnectError("refused\nforged line"))

    assert (text, note) == (None, summary.NOTE_FAILED)
    assert "ConnectError" in caplog.text and "forged line" not in caplog.text


@pytest.mark.parametrize(
    "reply",
    [
        GOOD_REPLY + " You should consider buying it back.",
        GOOD_REPLY + " It was sold because the valuation looked stretched.",
        GOOD_REPLY + " The investor wanted to lock in gains.",
        GOOD_REPLY + " A sound decision.",
        "AAA.L was sold after a 9.9% fall.",  # a figure that is not in the snapshot
        "",
        "AAA.L was sold. " * 100,
    ],
)
def test_reply_that_is_not_facts_only_is_rejected(reply):
    (text, note), _ = _summarise(reply)
    assert (text, note) == (None, summary.NOTE_REJECTED)


# --- through the real provider seam ------------------------------------------------------------


class FakeTool:
    def __init__(self, name):
        self.name = name
        self.description = name
        self.input_schema = {"type": "object", "properties": {}}


class FakeSession:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return SimpleNamespace(tools=[FakeTool(name) for name in MCP_TOOLSET])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[SimpleNamespace(text='{"AAA.L": 101.0}')], is_error=False)


def _patch_mcp(monkeypatch, module) -> FakeSession:
    session = FakeSession()

    @asynccontextmanager
    async def fake_mcp_session(url):
        assert url == MCP_URL
        yield session

    monkeypatch.setattr(module, "mcp_session", fake_mcp_session)
    return session


def _summarise_through_provider(cfg):
    return summary.summarise_context(SNAPSHOT, chat_turn=providers.run_configured_chat_turn, cfg=cfg)


def test_bedrock_offers_only_the_allowlist_and_refuses_a_write_tool(monkeypatch):
    session = _patch_mcp(monkeypatch, bedrock_agent)

    def tool_use(tool_id, name):
        return {"toolUse": {"toolUseId": tool_id, "name": name, "input": {"tickers": ["AAA.L"]}}}

    calls = [tool_use("t1", "get_live_prices"), tool_use("t2", "save_investment_plan")]
    responses = [
        {"output": {"message": {"role": "assistant", "content": calls}}},
        {"output": {"message": {"role": "assistant", "content": [{"text": GOOD_REPLY}]}}},
    ]
    seen = []

    class FakeBedrock:
        def converse(self, **kwargs):
            seen.append(copy.deepcopy(kwargs))
            return responses[len(seen) - 1]

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())
    cfg = SimpleNamespace(chat_provider="bedrock", app_env="aws", bedrock_model_id="test-model", mcp_server_url=MCP_URL)

    text, note = _summarise_through_provider(cfg)

    for request in seen:
        offered = {tool["toolSpec"]["name"] for tool in request["toolConfig"]["tools"]}
        assert offered == {"get_live_prices", "get_allocation"}
    assert [name for name, _ in session.calls] == ["get_live_prices"]
    assert (text, note) == (GOOD_REPLY, None)


def test_openai_compatible_offers_only_the_allowlist_and_refuses_a_write_tool(monkeypatch):
    session = _patch_mcp(monkeypatch, openai_compat_agent)

    def tool_call(call_id, name):
        call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}
        return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [call]}}]}

    responses = [
        tool_call("c1", "get_allocation"),
        tool_call("c2", "add_transaction"),
        {"choices": [{"message": {"role": "assistant", "content": GOOD_REPLY}}]},
    ]
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=responses[len(bodies) - 1])

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        openai_compat_agent.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    cfg = SimpleNamespace(
        chat_provider="ollama", app_env="local", chat_base_url=None, chat_model=None, mcp_server_url=MCP_URL
    )

    text, note = _summarise_through_provider(cfg)

    for body in bodies:
        assert {tool["function"]["name"] for tool in body["tools"]} == {"get_live_prices", "get_allocation"}
        assert body["max_tokens"] == summary.MAX_OUTPUT_TOKENS
    assert [name for name, _ in session.calls] == ["get_allocation"]
    assert (text, note) == (GOOD_REPLY, None)
