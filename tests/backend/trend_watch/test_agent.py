"""The trend-watch investigation, its guardrails and its read-only tool policy (#10476)."""

from __future__ import annotations

import json

import pytest

from backend.chat import openai_compat_agent
from backend.chat.local_tools import merge_tool_lists
from backend.chat.tool_switches import TREND_WATCH_TOOLS, ToolPolicy
from backend.config import TrendWatchConfig
from backend.trend_watch import agent, prompt
from backend.trend_watch.detect import detect

from ...chat.test_openai_compat_agent import (
    FakeCallToolResult,
    FakeSession,
    FakeTool,
    _completion,
    _fake_mcp_session_factory,
    _patch_http,
    _tool_call,
)
from .fixtures import FRESH_TURN_END, double_top, rising_benchmark

CFG = TrendWatchConfig()

# Tool names that change something. None may ever be on the trend-watch allowlist.
WRITE_TOOL_PREFIXES = (
    "create",
    "update",
    "delete",
    "set",
    "add",
    "remove",
    "fix",
    "apply",
    "record",
    "export",
    "write",
)
WRITE_TOOLS = {"create_github_issue", "export_file", "navigate_to_page", "create_price_trigger", "apply_data_fix"}


def _stock_specific():
    end = FRESH_TURN_END
    return detect(
        "TURN.L", double_top().iloc[:end], benchmark_levels=rising_benchmark().iloc[:end], benchmark_ticker="FTAL.L"
    )


def _market_wide():
    closes = double_top().iloc[:FRESH_TURN_END]
    return detect("BETA.L", closes, benchmark_levels=closes.copy(), benchmark_ticker="FTAL.L")


def _runner(reply: dict, calls=()):
    """A mocked model: makes ``calls`` (tool, result, is_error) through the policy, then replies."""

    async def run(message, policy):
        for tool, result, is_error in calls:
            assert policy.refusal(tool) is None
            policy.record(tool, {"ticker": "TURN.L"}, result, is_error)
        return "Here is my answer:\n" + json.dumps(reply)

    return run


async def _investigate(detection, runner):
    item = {"ticker": detection.ticker, "detection": detection.to_dict(), "context": {}}
    return await agent.investigate(item, detection, cfg=CFG, runner=runner)


async def test_holding_that_fell_with_its_benchmark_is_a_market_wide_move():
    result = await _investigate(
        _market_wide(),
        _runner(
            {"verdict": "market_wide_move", "summary": "It fell with the index.", "evidence": []},
            calls=[("get_peer_comparison", '{"peers": "all down about 20%"}', False)],
        ),
    )

    assert result["verdict"] == prompt.VERDICT_MARKET
    assert result["evidence"][0]["tool"] == "trend_watch.detect"
    assert result["evidence"][1]["tool"] == "trend_watch.benchmark_comparison"
    assert "price return" in result["evidence"][1]["finding"]


async def test_profit_warning_with_cited_evidence_is_idiosyncratic():
    reply = {
        "verdict": "idiosyncratic_deterioration",
        "summary": "The company issued a profit warning and cut its dividend.",
        "evidence": [
            {
                "tool": "search_web",
                "finding": "Profit warning: full-year profit to be 30% below expectations",
                "value": "-30% vs consensus",
                "source": "https://example.com/rns/profit-warning",
            },
            {"tool": "get_instrument_fundamentals", "finding": "Dividend cut", "value": "8p to 4p", "source": "x"},
        ],
    }
    calls = [
        ("search_web", "RNS: profit warning", False),
        ("get_instrument_fundamentals", '{"dividend_per_share": 4}', False),
    ]

    result = await _investigate(_stock_specific(), _runner(reply, calls))

    assert result["verdict"] == prompt.VERDICT_IDIOSYNCRATIC
    cited = [e for e in result["evidence"] if e["tool"] == "search_web"]
    assert cited[0]["source"] == "https://example.com/rns/profit-warning"
    assert [c["tool"] for c in result["tool_calls"]] == ["search_web", "get_instrument_fundamentals"]


async def test_stock_specific_claim_without_a_called_tool_is_inconclusive():
    reply = {
        "verdict": "idiosyncratic_deterioration",
        "summary": "A profit warning.",
        "evidence": [{"tool": "search_web", "finding": "warning", "value": "", "source": ""}],
    }

    result = await _investigate(_stock_specific(), _runner(reply))

    assert result["verdict"] == prompt.VERDICT_INCONCLUSIVE
    assert any("not called successfully" in note for note in result["notes"])


async def test_market_claim_contradicted_by_the_benchmark_is_inconclusive():
    reply = {"verdict": "market_wide_move", "summary": "Market fell.", "evidence": []}

    result = await _investigate(_stock_specific(), _runner(reply))

    assert result["verdict"] == prompt.VERDICT_INCONCLUSIVE


async def test_trade_instructions_are_withheld_from_the_report():
    reply = {
        "verdict": "idiosyncratic_deterioration",
        "summary": "Profit warning. You should sell this now; my price target is 80p.",
        "evidence": [
            {"tool": "search_web", "finding": "Profit warning issued", "value": "", "source": "rns"},
            {"tool": "search_web", "finding": "Consider selling before results", "value": "", "source": "blog"},
        ],
    }

    result = await _investigate(_stock_specific(), _runner(reply, [("search_web", "profit warning", False)]))

    assert result["summary"] is None
    findings = [e["finding"] for e in result["evidence"]]
    assert "Profit warning issued" in findings
    assert not any("selling" in f for f in findings)
    assert not prompt.advice_phrases(json.dumps(result))


async def test_without_a_model_the_verdict_comes_from_the_benchmark(monkeypatch):
    monkeypatch.setattr(agent.config, "mcp_server_url", None)

    market = await _investigate(_market_wide(), None)
    alone = await _investigate(_stock_specific(), None)

    assert (market["status"], market["verdict"]) == ("not_run", prompt.VERDICT_MARKET)
    assert alone["verdict"] == prompt.VERDICT_INCONCLUSIVE
    assert "Investigation not run" in alone["notes"][0]


async def test_a_failing_model_is_reported_not_raised():
    async def broken(message, policy):
        raise RuntimeError("Ollama is not running")

    result = await _investigate(_stock_specific(), broken)

    assert result["status"] == "failed"
    assert "Ollama is not running" in result["notes"][0]


@pytest.mark.parametrize(
    "text",
    [
        "You should sell the shares.",
        "Sell now before results.",
        "We recommend trimming the position.",
        "Consider selling half.",
        "Our price target is 120p.",
        "Set a stop-loss at 90p.",
        "This is a strong sell signal.",
        "The owner may want to exit.",
    ],
)
def test_advice_check_rejects_imperative_trade_language(text):
    assert prompt.advice_phrases(text)


@pytest.mark.parametrize(
    "text",
    [
        "The shares fell 20% after a profit warning.",
        "The board cut the dividend from 8p to 4p.",
        "Directors were selling shares in March.",
        "The discount to NAV widened to 15%.",
        "It moved with the FTSE All-Share.",
    ],
)
def test_advice_check_accepts_factual_descriptions(text):
    assert prompt.advice_phrases(text) == []


def test_allowlist_is_read_only():
    assert not TREND_WATCH_TOOLS & WRITE_TOOLS
    assert not [name for name in TREND_WATCH_TOOLS if name.startswith(WRITE_TOOL_PREFIXES)]
    assert all(name.startswith(("get_", "search_")) for name in TREND_WATCH_TOOLS)


def test_policy_hides_and_refuses_tools_outside_the_allowlist_and_caps_calls():
    policy = ToolPolicy(allowed=TREND_WATCH_TOOLS, max_calls=2)
    offered = merge_tool_lists([FakeTool("get_instrument_technicals"), FakeTool("create_github_issue")], None, policy)

    assert [tool.name for tool in offered] == ["get_instrument_technicals"]
    assert "not available" in policy.refusal("create_github_issue")
    policy.record("search_web", {}, "x", False)
    policy.record("search_web", {}, "y", False)
    assert "limit of 2" in policy.refusal("search_web")


async def test_chat_loop_enforces_the_policy(monkeypatch):
    session = FakeSession(
        tools=[FakeTool("get_instrument_technicals"), FakeTool("create_github_issue")],
        tool_results={"get_instrument_technicals": FakeCallToolResult('{"trend": "downtrend"}')},
    )
    monkeypatch.setattr(openai_compat_agent, "mcp_session", _fake_mcp_session_factory(session))
    requests = _patch_http(
        monkeypatch,
        [
            _completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        _tool_call("c1", "create_github_issue", '{"title": "x"}'),
                        _tool_call("c2", "get_instrument_technicals", '{"ticker": "TURN.L"}'),
                    ],
                }
            ),
            _completion({"role": "assistant", "content": "{}"}),
        ],
    )
    policy = ToolPolicy(allowed=TREND_WATCH_TOOLS, max_calls=5)

    await openai_compat_agent.run_chat_turn(
        "investigate",
        [],
        mcp_server_url="http://localhost:8001/mcp",
        base_url="http://localhost:11434/v1",
        model="m",
        tool_policy=policy,
    )

    offered = [tool["function"]["name"] for tool in json.loads(requests[0].content)["tools"]]
    assert offered == ["get_instrument_technicals"]
    assert session.calls == [("get_instrument_technicals", {"ticker": "TURN.L"})]
    assert [call["tool"] for call in policy.calls] == ["get_instrument_technicals"]


async def test_zero_values_are_kept_in_evidence():
    reply = {
        "verdict": "idiosyncratic_deterioration",
        "summary": "Dividend suspended.",
        "evidence": [{"tool": "get_instrument_fundamentals", "finding": "Dividend", "value": 0, "source": "x"}],
    }

    result = await _investigate(
        _stock_specific(), _runner(reply, [("get_instrument_fundamentals", '{"dividend": 0}', False)])
    )

    assert result["evidence"][-1]["value"] == "0"


async def test_market_verdict_without_a_benchmark_says_so():
    closes = double_top().iloc[:FRESH_TURN_END]
    no_benchmark = detect("SOLO.L", closes)

    result = await _investigate(no_benchmark, _runner({"verdict": "market_wide_move", "summary": "", "evidence": []}))

    assert result["verdict"] == prompt.VERDICT_MARKET
    assert any("no benchmark" in note for note in result["notes"])
