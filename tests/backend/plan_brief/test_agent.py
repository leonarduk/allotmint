"""LLM step of the plan-drift brief (#10475): read-only tools, evidence and no advice.

The LLM is always mocked: either the provider loop is replaced outright, or
the real OpenAI-compatible loop runs against a fake HTTP completion endpoint
and a fake MCP session, so no network is touched.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.chat import openai_compat_agent
from backend.chat.tool_switches import is_read_only_tool_name
from backend.chat.turn_limits import TurnLimits
from backend.common.allocation_policy import AllocationPolicy
from backend.plan_brief import agent
from backend.plan_brief.drift import build_facts
from backend.plan_brief.prompt import SYSTEM_PROMPT, advice_violations, drift_figure_mismatches
from tests.backend.plan_brief.conftest import TODAY, portfolio
from tests.chat.test_openai_compat_agent import (
    FakeCallToolResult,
    FakeSession,
    FakeTool,
    _completion,
    _fake_mcp_session_factory,
    _patch_http,
    _tool_call,
)

CFG = SimpleNamespace(chat_provider="ollama", app_env="local", chat_model=None, chat_base_url=None, bedrock_model_id="")

MARKET_RATES = {
    "units": "percent",
    "source": "Bank of England IADB",
    "latest": {"bank_rate": {"value": 2.75, "date": "2026-10-08", "code": "IUDBEDR"}},
}

GOOD_PROSE = (
    "Equity is 6.0pp above its 60% target (£6,000) and long gilts are 10.0pp below (£10,000), "
    "both outside the 5pp band. Bank Rate is 2.75%, so the Bank Rate trigger has fired. "
    "The plan review date has passed."
)


def _reply(prose=GOOD_PROSE, evidence=True, verdict="fired"):
    return json.dumps(
        {
            "triggers": [
                {
                    "trigger": "Bank Rate below 3%",
                    "verdict": verdict,
                    "reason": "Bank Rate is 2.75%, below 3%.",
                    "evidence": (
                        [
                            {
                                "tool": "get_market_rates",
                                "field": "latest.bank_rate.value",
                                "value": 2.75,
                                "source": "Bank of England IADB",
                                "as_of": "2026-10-08",
                            }
                        ]
                        if evidence
                        else []
                    ),
                }
            ],
            "assumptions": [
                {
                    "key": "bank_rate_pct",
                    "status": "differs",
                    "current_value": 2.75,
                    "reason": "Assumed 4.0%, now 2.75%.",
                    "evidence": [{"tool": "get_market_rates", "field": "latest.bank_rate.value", "value": 2.75}],
                }
            ],
            "prose": prose,
        }
    )


@pytest.fixture()
def facts(plan):
    return build_facts(plan, portfolio(), AllocationPolicy(tolerance_pct=5.0), [], TODAY)


def _limits_with_rates_call():
    limits = TurnLimits(allowed_tools=agent.READ_ONLY_TOOLS)
    limits.record_call("get_market_rates", {"series": ["bank_rate"]}, json.dumps(MARKET_RATES), False)
    return limits


# --------------------------------------------------------------------------- read-only allowlist

# Write tools exposed by the allotmint-pro MCP server today.
KNOWN_WRITE_TOOLS = {
    "add_instrument",
    "create_issue",
    "create_price_trigger",
    "update_price_trigger",
    "delete_price_trigger",
}


def test_allowlist_has_no_write_tools():
    assert agent.READ_ONLY_TOOLS.isdisjoint(KNOWN_WRITE_TOOLS)
    assert all(is_read_only_tool_name(name) for name in agent.READ_ONLY_TOOLS)
    assert not any(is_read_only_tool_name(name) for name in KNOWN_WRITE_TOOLS)
    assert "navigate_to_page" not in agent.READ_ONLY_TOOLS and "export_file" not in agent.READ_ONLY_TOOLS


# --------------------------------------------------------------------------- no advice


@pytest.mark.parametrize(
    "text",
    [
        "Sell £6,000 of equity.",
        "You should buy more gilts.",
        "Equity is over target. Rebalance into bonds.",
        "We recommend topping up the ISA.",
        "Consider switching to a cheaper tracker.",
        "- Buy VWRL.L",
        "It would be sensible to trim equities.",
        "Move the cash into a money market fund.",
    ],
)
def test_advice_language_is_rejected(text):
    assert advice_violations(text), text


@pytest.mark.parametrize(
    "text",
    [
        GOOD_PROSE,
        "There were 2 purchases and no sales since the last brief; contributions totalled £4,000.",
        "The ISA holds £4,000 of cash received on 2026-09-18, with no purchase since.",
    ],
)
def test_factual_language_passes(text):
    assert advice_violations(text) == []


def test_system_prompt_forbids_advice():
    assert "Never recommend" in SYSTEM_PROMPT and "never name a product" in SYSTEM_PROMPT


def test_fallback_prose_is_itself_advice_free(facts):
    prose = agent.fallback_prose(facts)
    assert advice_violations(prose) == []
    assert drift_figure_mismatches(prose, facts["drift"]) == []
    assert "6.0pp above" in prose and "£6,000" in prose


def test_brief_with_advice_prose_falls_back_to_deterministic_text(plan, facts):
    result = agent.interpret_reply(
        plan, facts, _reply(prose="Equity is high. Sell £6,000 of it."), _limits_with_rates_call()
    )
    assert result["prose_source"] == "deterministic"
    assert result["output_check"]["passed"] is False
    assert "Sell £6,000" not in result["prose"]
    assert advice_violations(result["prose"]) == []


def test_drift_figures_that_disagree_with_the_table_are_rejected(plan, facts):
    result = agent.interpret_reply(
        plan, facts, _reply(prose="Equity is 7.5pp above target."), _limits_with_rates_call()
    )
    assert result["prose_source"] == "deterministic"
    assert any("7.5pp" in p for p in result["output_check"]["problems"])


# --------------------------------------------------------------------------- verdicts and evidence


def test_fired_trigger_keeps_evidence_and_the_tool_call_behind_it(plan, facts):
    result = agent.interpret_reply(plan, facts, _reply(), _limits_with_rates_call())
    [verdict] = result["triggers"]
    assert verdict["verdict"] == "fired"
    assert verdict["evidence"][0]["value"] == 2.75
    assert verdict["evidence"][0]["source"] == "Bank of England IADB"
    assert verdict["tool_calls"][0]["tool"] == "get_market_rates"
    assert result["prose_source"] == "agent"
    [assumption] = result["assumptions"]
    assert assumption["status"] == "differs" and assumption["current_value"] == 2.75


def test_verdict_without_evidence_is_cant_evaluate(plan, facts):
    [verdict] = agent.interpret_reply(plan, facts, _reply(evidence=False), _limits_with_rates_call())["triggers"]
    assert verdict["verdict"] == "cant_evaluate"


def test_evidence_from_a_tool_never_called_is_ignored(plan, facts):
    limits = TurnLimits(allowed_tools=agent.READ_ONLY_TOOLS)  # no calls made
    [verdict] = agent.interpret_reply(plan, facts, _reply(verdict="not_fired"), limits)["triggers"]
    assert verdict["verdict"] == "cant_evaluate"


def test_evidence_value_must_match_what_the_tool_returned(plan, facts):
    limits = TurnLimits(allowed_tools=agent.READ_ONLY_TOOLS)
    limits.record_call("get_market_rates", {}, json.dumps({"latest": {"bank_rate": {"value": 4.0}}}), False)
    [verdict] = agent.interpret_reply(plan, facts, _reply(), limits)["triggers"]
    # The reply cites 2.75 but the call returned 4.0.
    assert verdict["verdict"] == "cant_evaluate"
    assert verdict["evidence"] == []


@pytest.mark.parametrize(
    ("result", "field", "value", "ok"),
    [
        ({"latest": {"bank_rate": {"value": 2.75}}}, "latest.bank_rate.value", 2.75, True),
        ({"latest": {"bank_rate": {"value": 2.75}}}, "latest.bank_rate.value", 3.0, False),
        # A boolean must match the cited field; "true" elsewhere in the result is not enough.
        ({"is_error": True, "flag": False}, "flag", True, False),
        ({"is_error": True, "flag": True}, "flag", True, True),
        ({"is_error": True}, "missing.field", True, False),
        # Field not resolvable: a number may still be confirmed from the text.
        ({"rows": [{"bank_rate": 2.75}]}, "bank_rate", 2.75, True),
    ],
)
def test_value_check_uses_the_cited_field(result, field, value, ok):
    assert agent._value_in(value, field, json.dumps(result)) is ok


def test_unrecognised_verdict_says_so(plan, facts):
    reply = json.loads(_reply())
    reply["triggers"][0]["verdict"] = "probably"
    [verdict] = agent.interpret_reply(plan, facts, json.dumps(reply), _limits_with_rates_call())["triggers"]
    assert verdict["verdict"] == "cant_evaluate"
    assert verdict["reason"].startswith("Unrecognised verdict 'probably'")


def test_advice_in_a_verdict_reason_is_removed(plan, facts):
    reply = json.loads(_reply())
    reply["triggers"][0]["reason"] = "Bank Rate is 2.75%, so you should buy gilts."
    [verdict] = agent.interpret_reply(plan, facts, json.dumps(reply), _limits_with_rates_call())["triggers"]
    assert verdict["verdict"] == "fired"
    assert verdict["reason"] == "(removed: wording read as advice)"


def test_errored_calls_are_never_cited_as_evidence(plan, facts):
    limits = _limits_with_rates_call()
    limits.record_call("get_market_rates", {"series": ["gilt_10y"]}, "Tool call failed: boom", True)
    [verdict] = agent.interpret_reply(plan, facts, _reply(), limits)["triggers"]
    assert verdict["verdict"] == "fired"
    assert [call["is_error"] for call in verdict["tool_calls"]] == [False]


def test_reply_wrapped_in_a_fenced_array_is_still_read(plan, facts):
    reply = "Here you go:\n```json\n[" + _reply() + "]\n```"
    [verdict] = agent.interpret_reply(plan, facts, reply, _limits_with_rates_call())["triggers"]
    assert verdict["verdict"] == "fired"


def test_missing_trigger_or_unparseable_reply_is_cant_evaluate_not_not_fired(plan, facts):
    for reply in ("not json at all", json.dumps({"triggers": [], "prose": GOOD_PROSE})):
        [verdict] = agent.interpret_reply(plan, facts, reply, _limits_with_rates_call())["triggers"]
        assert verdict["verdict"] == "cant_evaluate"


async def test_without_mcp_server_every_trigger_is_cant_evaluate(plan, facts):
    result = await agent.run_agent(plan, facts, today="2026-10-09", cfg=CFG, mcp_server_url=None)
    assert [t["verdict"] for t in result["triggers"]] == ["cant_evaluate"]
    assert "not configured" in result["triggers"][0]["reason"]
    assert result["agent"]["ran"] is False


async def test_llm_failure_still_yields_a_deterministic_brief(plan, facts):
    async def broken(*args, **kwargs):
        raise RuntimeError("model down")

    result = await agent.run_agent(
        plan, facts, today="2026-10-09", cfg=CFG, mcp_server_url="http://mcp", chat_turn=broken
    )
    assert result["triggers"][0]["verdict"] == "cant_evaluate"
    assert result["prose_source"] == "deterministic"


# --------------------------------------------------------------------------- through the real provider loop


async def test_bank_rate_trigger_fires_from_mocked_market_rates_via_provider_loop(monkeypatch, plan, facts):
    session = FakeSession(
        tools=[FakeTool("get_market_rates"), FakeTool("create_issue"), FakeTool("get_portfolio")],
        tool_results={
            "get_market_rates": FakeCallToolResult(json.dumps(MARKET_RATES)),
            "create_issue": FakeCallToolResult("should never run"),
        },
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
                        _tool_call("c1", "get_market_rates", '{"series": ["bank_rate"]}'),
                        # Not offered, but a model may name it anyway: it must be refused.
                        _tool_call("c2", "create_issue", '{"title": "x"}'),
                    ],
                }
            ),
            {
                **_completion({"role": "assistant", "content": _reply()}),
                "usage": {"prompt_tokens": 900, "completion_tokens": 300},
            },
        ],
    )

    result = await agent.run_agent(plan, facts, today="2026-10-09", cfg=CFG, mcp_server_url="http://mcp")

    offered = {tool["function"]["name"] for tool in json.loads(requests[0].content)["tools"]}
    assert offered == {"get_market_rates", "get_portfolio"}
    assert json.loads(requests[0].content)["max_tokens"] == agent.MAX_OUTPUT_TOKENS
    assert session.calls == [("get_market_rates", {"series": ["bank_rate"]})]
    [verdict] = result["triggers"]
    assert verdict["verdict"] == "fired"
    assert verdict["evidence"][0]["value"] == 2.75
    assert "2.75" in verdict["tool_calls"][0]["result"]
    refused = [call for call in result["agent"]["tool_calls"] if call["tool"] == "create_issue"]
    assert refused and refused[0]["is_error"] is True
    assert result["agent"]["usage"] == {"input_tokens": 900, "output_tokens": 300}
    assert result["agent"]["model"] == "qwen3.5:9b"
