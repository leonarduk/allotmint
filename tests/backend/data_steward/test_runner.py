"""Tests for the data steward agent (#10471). The LLM and MCP tools are fakes: no network."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Tuple

import pytest

from backend.chat import tool_switches
from backend.chat.tool_switches import DATA_STEWARD_READ_ONLY_TOOLS, data_steward_tool_allowed
from backend.data_steward import runner
from backend.data_steward.llm import LLMReply, ToolCall, estimate_cost_usd, to_bedrock_messages
from backend.data_steward.runner import StewardLimits, build_verdict, parse_verdict, run_steward
from backend.data_steward.tools import McpStewardTools

# Every tool the allotmint-pro MCP server registers that writes something, sends
# something out, or reaches the web. None may ever be on the steward's allowlist.
WRITE_OR_EXTERNAL_TOOLS = {
    "add_instrument",
    "create_price_trigger",
    "update_price_trigger",
    "delete_price_trigger",
    "create_github_issue",
    "fetch_web_page",
    "search_web",
    "backfill_history",
}

JEGI_ISSUE = {
    "id": "OUTLIERS:JEGI:L",
    "type": "OUTLIERS",
    "severity": "low",
    "entity": {"ticker": "JEGI", "exchange": "L"},
    "description": "JEGI.L has a row dated 1969-12-31 and a 10x step on 2024-05-01.",
    "suggested_fix": "Review the series.",
    "preview": {},
    "fixable": False,
}
STALE_ISSUE = {
    "id": "STALE_SERIES:VWRL:L",
    "type": "STALE_SERIES",
    "severity": "medium",
    "entity": {"ticker": "VWRL", "exchange": "L"},
    "description": "VWRL.L last price is 20 days old.",
    "suggested_fix": "Refetch the series.",
    "preview": {},
    "fixable": True,
}
WRONG_EXCHANGE_ISSUE = {
    "id": "WRONG_EXCHANGE:alex:isa:ABC.N",
    "type": "WRONG_EXCHANGE",
    "severity": "high",
    "entity": {"owner": "alex", "account": "isa", "holding": "ABC.N"},
    "description": "ABC.N should be ABC.L.",
    "suggested_fix": "Change exchange.",
    "preview": {},
    "fixable": True,
}
UNHELD_ISSUE = {
    "id": "GAPS:ZZZ:L",
    "type": "GAPS",
    "severity": "high",
    "entity": {"ticker": "ZZZ", "exchange": "L"},
    "description": "gaps",
    "suggested_fix": "Refetch.",
    "preview": {},
    "fixable": True,
}

PORTFOLIO = {
    "owner": "alex",
    "accounts": [
        {
            "account_type": "isa",
            "holdings": [
                {"ticker": "JEGI.L", "market_value_gbp": 2500.0},
                {"ticker": "VWRL.L", "market_value_gbp": 7000.0},
                {"ticker": "ABC.N", "market_value_gbp": 500.0},
            ],
        }
    ],
}


class FakeTools:
    def __init__(self, issues: List[Dict[str, Any]], *, fail: set[str] | None = None) -> None:
        self.issues = issues
        self.fail = fail or set()
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    async def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": name, "description": name, "input_schema": {"type": "object"}}
            for name in sorted(DATA_STEWARD_READ_ONLY_TOOLS)
        ]

    async def call(self, name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
        self.calls.append((name, arguments))
        if name in self.fail:
            return f"{name} exploded", True
        if name == "get_data_quality_report":
            return json.dumps({"total_count": len(self.issues), "issues": self.issues, "check_errors": []}), False
        if name == "list_owners":
            return json.dumps([{"owner": "alex"}]), False
        if name == "get_portfolio":
            return json.dumps(PORTFOLIO), False
        if name == "get_instrument":
            return (
                json.dumps(
                    {"timeseries": [{"Date": "1969-12-31", "Close": 1.0}, {"Date": "2024-05-01", "Close": 95.0}]}
                ),
                False,
            )
        return json.dumps({"ok": name}), False


class ScriptedLLM:
    """Replies from a per-issue script, keyed by a substring of the issue brief."""

    def __init__(self, scripts: Dict[str, List[LLMReply]]) -> None:
        self.scripts = {key: list(replies) for key, replies in scripts.items()}
        self.seen_tools: List[List[str]] = []

    async def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        self.seen_tools.append([tool["name"] for tool in tools])
        brief = messages[1]["content"]
        for key, replies in self.scripts.items():
            if key in brief:
                if not replies:
                    raise AssertionError(f"script for {key} ran out")
                return replies.pop(0)
        raise AssertionError("no script for this issue")


def _verdict(**fields: Any) -> LLMReply:
    return LLMReply(content=json.dumps(fields), input_tokens=100, output_tokens=20)


def _tool_call(name: str, arguments: Dict[str, Any], call_id: str = "c1") -> LLMReply:
    return LLMReply(content="", tool_calls=[ToolCall(call_id, name, arguments)], input_tokens=50, output_tokens=10)


def _run(llm: Any, tools: Any, limits: StewardLimits = StewardLimits()) -> Dict[str, Any]:
    return asyncio.run(run_steward(llm, tools, provider="ollama", model="qwen", limits=limits))


# ───────────── read-only allowlist ─────────────


def test_allowlist_contains_no_write_tools() -> None:
    assert DATA_STEWARD_READ_ONLY_TOOLS.isdisjoint(WRITE_OR_EXTERNAL_TOOLS)
    for name in DATA_STEWARD_READ_ONLY_TOOLS:
        assert name.startswith(("get_", "list_", "read_")), f"{name} does not look read-only"


def test_allowlist_refuses_switched_off_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_switches, "tool_enabled", lambda name: name != "get_instrument")
    assert not data_steward_tool_allowed("get_instrument")
    assert data_steward_tool_allowed("get_data_freshness")
    assert not data_steward_tool_allowed("create_price_trigger")


class _FakeMcpTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = name
        self.input_schema = {"type": "object"}


class _FakeSession:
    def __init__(self) -> None:
        self.called: List[str] = []

    async def list_tools(self) -> Any:
        class Result:
            tools = [
                _FakeMcpTool(n) for n in ("get_instrument", "create_price_trigger", "add_instrument", "get_portfolio")
            ]

        return Result()

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.called.append(name)
        raise AssertionError("not reached in these tests")


def test_mcp_tools_hide_and_refuse_write_tools() -> None:
    session = _FakeSession()
    tools = McpStewardTools(session)
    names = [tool["name"] for tool in asyncio.run(tools.list_tools())]
    assert names == ["get_instrument", "get_portfolio"]
    text, is_error = asyncio.run(tools.call("create_price_trigger", {"ticker": "X"}))
    assert is_error and "allowlist" in text
    assert session.called == []


def test_model_asking_for_a_write_tool_is_refused_and_recorded() -> None:
    tools = FakeTools([STALE_ISSUE])
    real_call = tools.call

    async def guarded(name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
        if name not in DATA_STEWARD_READ_ONLY_TOOLS:
            return "refused", True
        return await real_call(name, arguments)

    tools.call = guarded  # type: ignore[method-assign]
    llm = ScriptedLLM(
        {"VWRL": [_tool_call("add_instrument", {"ticker": "VWRL.L"}), _verdict(verdict="needs_human", confidence=0.4)]}
    )
    report = _run(llm, tools)
    item = report["items"][0]
    assert item["evidence"][0] == {
        "tool": "add_instrument",
        "arguments": {"ticker": "VWRL.L"},
        "result": "refused",
        "truncated": False,
        "is_error": True,
    }
    assert all(name in DATA_STEWARD_READ_ONLY_TOOLS for seen in llm.seen_tools for name in seen)


# ───────────── the run ─────────────


def test_run_reports_each_held_issue_with_verdict_evidence_and_exposure() -> None:
    tools = FakeTools([JEGI_ISSUE, STALE_ISSUE, WRONG_EXCHANGE_ISSUE, UNHELD_ISSUE])
    llm = ScriptedLLM(
        {
            "JEGI": [
                _tool_call("get_instrument", {"ticker": "JEGI.L", "include": ["timeseries"]}),
                _verdict(
                    verdict="needs_human",
                    root_cause="epoch_zero_row+unadjusted_split",
                    summary="A 1969-12-31 row and an unrecorded 10x step on 2024-05-01.",
                    checked=["timeseries"],
                    unclear=["split ratio"],
                    confidence=0.8,
                ),
            ],
            "VWRL": [_verdict(verdict="fix_available", root_cause="source_outage", confidence=0.9)],
            "ABC.N": [_verdict(verdict="fix_available", root_cause="wrong_exchange", confidence=1.4)],
        }
    )
    report = _run(llm, tools)

    assert report["status"] == "ok"
    assert report["portfolio_value_gbp"] == 10000.0
    assert report["skipped_unheld"] == 1
    assert [item["issue_id"] for item in report["items"]] == [
        WRONG_EXCHANGE_ISSUE["id"],  # high severity first
        STALE_ISSUE["id"],
        JEGI_ISSUE["id"],
    ]
    by_id = {item["issue_id"]: item for item in report["items"]}
    jegi = by_id[JEGI_ISSUE["id"]]
    assert jegi["verdict"] == "needs_human"
    assert jegi["root_cause"] == "epoch_zero_row+unadjusted_split"
    assert jegi["exposure_gbp"] == 2500.0 and jegi["exposure_pct"] == 25.0
    assert jegi["evidence"][0]["tool"] == "get_instrument"
    assert "1969-12-31" in jegi["evidence"][0]["result"]
    assert "proposed_fix" not in jegi

    stale = by_id[STALE_ISSUE["id"]]
    assert stale["proposed_fix"] == {
        "method": "POST",
        "path": "/data-quality/issues/STALE_SERIES%3AVWRL%3AL/fix",
        "issue_id": STALE_ISSUE["id"],
        "description": "Refetch the series.",
    }
    assert by_id[WRONG_EXCHANGE_ISSUE["id"]]["confidence"] == 1.0
    assert report["totals"] == {"input_tokens": 350, "output_tokens": 70, "tool_calls": 1, "cost_usd": 0.0}


def test_tool_budget_per_issue_is_enforced() -> None:
    tools = FakeTools([STALE_ISSUE])
    replies = [_tool_call("get_data_freshness", {"ticker": "VWRL.L"}, f"c{i}") for i in range(5)]
    llm = ScriptedLLM({"VWRL": replies + [_verdict(verdict="needs_human")]})
    report = _run(llm, tools, StewardLimits(max_issues=5, max_tool_calls_per_issue=2))
    item = report["items"][0]
    assert len(item["evidence"]) == 2
    assert report["totals"]["tool_calls"] == 2
    # After the budget the model is asked once more and its extra tool call is not run.
    assert item["verdict"] == "needs_human"
    assert item["root_cause"] == "undetermined"


def test_max_issues_caps_the_run() -> None:
    tools = FakeTools([JEGI_ISSUE, STALE_ISSUE, WRONG_EXCHANGE_ISSUE])
    llm = ScriptedLLM({"ABC.N": [_verdict(verdict="needs_human")]})
    report = _run(llm, tools, StewardLimits(max_issues=1))
    assert report["issues_investigated"] == 1
    assert report["skipped_over_limit"] == 2


def test_fix_available_without_automated_fix_is_downgraded() -> None:
    verdict = build_verdict(JEGI_ISSUE, json.dumps({"verdict": "fix_available", "root_cause": "x"}))
    assert verdict["verdict"] == "needs_human"
    assert "proposed_fix" not in verdict


def test_not_a_problem_carries_an_allowlist_reason() -> None:
    verdict = build_verdict(JEGI_ISSUE, '{"verdict": "not_a_problem", "allowlist_reason": "recorded split"}')
    assert verdict["allowlist_reason"] == "recorded split"


def test_parse_verdict_handles_fences_and_think_blocks() -> None:
    text = (
        '<think>{"verdict": "fix_available"}</think>Here:\n```json\n{"verdict": "needs_human", "confidence": 0.5}\n```'
    )
    assert parse_verdict(text) == {"verdict": "needs_human", "confidence": 0.5}
    assert parse_verdict("no json here") is None


def test_unparseable_reply_becomes_needs_human_with_raw_reply() -> None:
    verdict = build_verdict(STALE_ISSUE, "I think it is fine")
    assert verdict["verdict"] == "needs_human"
    assert verdict["raw_reply"] == "I think it is fine"


def test_llm_failure_is_reported_on_the_item_and_run_continues() -> None:
    class Boom:
        async def complete(self, messages: Any, tools: Any) -> LLMReply:
            if "VWRL" in messages[1]["content"]:
                raise RuntimeError("model down")
            return _verdict(verdict="needs_human")

    report = _run(Boom(), FakeTools([STALE_ISSUE, JEGI_ISSUE]))
    assert report["status"] == "partial"
    by_id = {item["issue_id"]: item for item in report["items"]}
    assert by_id[STALE_ISSUE["id"]]["verdict"] == "error"
    assert "model down" in by_id[STALE_ISSUE["id"]]["error"]
    assert by_id[JEGI_ISSUE["id"]]["verdict"] == "needs_human"


def test_issue_report_failure_makes_an_error_report() -> None:
    report = _run(ScriptedLLM({}), FakeTools([], fail={"get_data_quality_report"}))
    assert report["status"] == "error"
    assert report["errors"][0]["stage"] == "setup"
    assert "exploded" in report["errors"][0]["error"]


def test_holdings_failure_keeps_every_issue_and_reports_it() -> None:
    tools = FakeTools([UNHELD_ISSUE], fail={"get_portfolio"})
    llm = ScriptedLLM({"ZZZ": [_verdict(verdict="needs_human")]})
    report = _run(llm, tools)
    assert report["status"] == "partial"
    assert report["errors"][0]["stage"] == "holdings"
    assert report["items"][0]["exposure_gbp"] is None


def test_runner_never_calls_a_tool_off_the_allowlist() -> None:
    tools = FakeTools([JEGI_ISSUE, STALE_ISSUE])
    llm = ScriptedLLM(
        {
            "JEGI": [_tool_call("get_instrument", {"ticker": "JEGI.L"}), _verdict(verdict="needs_human")],
            "VWRL": [_verdict(verdict="fix_available")],
        }
    )
    _run(llm, tools)
    assert {name for name, _ in tools.calls} <= DATA_STEWARD_READ_ONLY_TOOLS


# ───────────── helpers ─────────────


def test_exposure_scopes_holding_issues_to_their_account() -> None:
    holdings = [
        runner.Holding("alex", "isa", "ABC.N", 500.0),
        runner.Holding("alex", "sipp", "ABC.N", 300.0),
        runner.Holding("sam", "isa", "ABC.N", 200.0),
    ]
    assert runner.exposure(WRONG_EXCHANGE_ISSUE["entity"], holdings, 1000.0) == (500.0, 50.0)
    assert runner.exposure({"ticker": "ABC", "exchange": "N"}, holdings, 1000.0) == (1000.0, 100.0)


def test_cost_estimate() -> None:
    assert estimate_cost_usd("ollama", "qwen", 10_000, 1_000) == 0.0
    assert estimate_cost_usd("deepseek", "deepseek-chat", 1_000_000, 1_000_000) == pytest.approx(1.37)
    assert estimate_cost_usd("bedrock", "unknown-model", 1, 1) is None


def test_cost_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_STEWARD_COST_PER_MTOK", "3,15")
    assert estimate_cost_usd("bedrock", "anything", 1_000_000, 1_000_000) == 18.0


def test_bedrock_messages_alternate_and_merge_tool_results_with_final_prompt() -> None:
    system, messages = to_bedrock_messages(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "brief"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [ToolCall("a", "get_instrument", {}), ToolCall("b", "get_data_freshness", {})],
            },
            {"role": "tool", "tool_call_id": "a", "content": "one", "is_error": False},
            {"role": "tool", "tool_call_id": "b", "content": "two", "is_error": True},
            {"role": "user", "content": "final please"},
        ]
    )
    assert system == [{"text": "sys"}]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    results, final = messages[2]["content"][:2], messages[2]["content"][2]
    assert [block["toolResult"]["status"] for block in results] == ["success", "error"]
    assert final == {"text": "final please"}
    assert [block["toolUse"]["name"] for block in messages[1]["content"]] == ["get_instrument", "get_data_freshness"]
