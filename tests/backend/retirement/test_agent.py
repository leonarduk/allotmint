"""Narrative guardrails (#10484): read-only tool allowlist, no new figures, no advice wording."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.chat import providers, tool_switches
from backend.retirement import agent
from backend.retirement.readiness import ADVISER_NOTE

WRITE_VERBS = ("set", "save", "update", "delete", "add", "create", "write", "approve", "refresh", "import", "record")


def _report() -> dict:
    return {
        "run_date": "2030-01-15",
        "inputs": {"retirement_age": 60},
        "results": {
            "projection": {"projected_pot_nominal_gbp": 250000.0, "start_pot_real_gbp": 200000.0},
            "simulation": {
                "horizon_years": 30,
                "windows": {"count": 4},
                "sustainable_income": [
                    {"survival_pct": 95.0, "income_gbp": 9100.55},
                    {"survival_pct": 100.0, "income_gbp": 8700.25},
                ],
                "worst": {"start_year": 1992, "end_year": 2021, "sustainable_income_gbp": 8700.25},
                "median": {"start_year": 1993, "end_year": 2022, "sustainable_income_gbp": 9400.0},
                "best": {"start_year": 1994, "end_year": 2023, "sustainable_income_gbp": 9900.0},
                "floor": None,
            },
        },
        "attribution": None,
        "assumption_changes": [{"label": "retirement age"}],
        "market": {"flags": []},
        "caveats": ["Fees, charges and taxes are not modelled; returns are gross.", ADVISER_NOTE],
    }


def test_allowlist_is_exactly_the_read_only_tools():
    assert agent.READ_ONLY_TOOLS == {
        "get_market_rates",
        "get_pension_forecast",
        "get_investment_plan",
        "summarise_transactions",
    }
    for name in agent.READ_ONLY_TOOLS:
        assert name.startswith(("get_", "summarise_")), name
        assert not any(verb in name.split("_") for verb in WRITE_VERBS), name


def test_allowlist_filters_and_refuses_other_tools():
    tools = [SimpleNamespace(name=n) for n in ("get_market_rates", "save_plan", "get_investment_plan")]
    offered = tool_switches.allowed_tools_only(tools, agent.READ_ONLY_TOOLS)
    assert [t.name for t in offered] == ["get_market_rates", "get_investment_plan"]
    assert tool_switches.allowed_tools_only(tools, None) == tools
    assert tool_switches.tool_allowed("get_market_rates", agent.READ_ONLY_TOOLS)
    assert not tool_switches.tool_allowed("save_plan", agent.READ_ONLY_TOOLS)
    assert "not in this conversation's allowed tools" in tool_switches.refused_message(
        "save_plan", agent.READ_ONLY_TOOLS
    )


def test_provider_passes_allowlist_to_the_agent(monkeypatch):
    seen = {}

    async def fake_turn(message, history, **kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(providers.bedrock_agent, "run_chat_turn", fake_turn)
    cfg = SimpleNamespace(chat_provider="bedrock", app_env="aws", bedrock_model_id="m")
    reply = asyncio.run(
        providers.run_configured_chat_turn(
            "facts", [], cfg=cfg, mcp_server_url="http://mcp", allowed_tools=agent.READ_ONLY_TOOLS
        )
    )
    assert reply == "ok"
    assert seen["allowed_tools"] == agent.READ_ONLY_TOOLS


def test_default_llm_uses_the_allowlist(monkeypatch):
    from backend.config import config

    seen = {}

    async def fake_turn(message, history, **kwargs):
        seen.update(kwargs)
        return "summary"

    monkeypatch.setattr(config, "mcp_server_url", "http://mcp", raising=False)
    monkeypatch.setattr(providers, "run_configured_chat_turn", fake_turn)
    llm = agent._default_llm()
    assert llm is not None and llm("system", "facts") == "summary"
    assert seen["allowed_tools"] == agent.READ_ONLY_TOOLS


def test_template_used_without_a_model(monkeypatch):
    monkeypatch.setattr(agent, "_default_llm", lambda: None)
    narrative = agent.write_narrative(_report())
    assert narrative["source"] == "template"
    assert "£8,700.25" in narrative["text"]


def test_llm_narrative_with_only_reported_figures_is_kept():
    text = (
        "In 100% of the 4 historical windows the pot sustained £8,700.25 a year; the worst began in 1992. "
        + ADVISER_NOTE
    )
    narrative = agent.write_narrative(_report(), llm=lambda system, facts: text)
    assert narrative == {"text": text, "source": "llm", "note": None}


def test_llm_narrative_with_a_new_figure_is_rejected():
    text = "The pot sustained £8,700.25 a year, roughly a 4.35% withdrawal rate."
    narrative = agent.write_narrative(_report(), llm=lambda system, facts: text)
    assert narrative["source"] == "template"
    assert "rejected" in narrative["note"]
    assert "4.35" not in narrative["text"]


@pytest.mark.parametrize(
    "text",
    [
        "You should withdraw £8,700.25 a year.",
        "We recommend retiring at 60.",
        "Consider switching to more gilts.",
        "It is safe to withdraw £8,700.25.",
        "You could safely withdraw £9,100.55.",
        "Buy more equity before 2030.",
    ],
)
def test_advice_wording_is_detected_and_rejected(text):
    assert agent.advice_violations(text)
    narrative = agent.write_narrative(_report(), llm=lambda system, facts: text)
    assert narrative["source"] == "template"


def test_model_failure_falls_back_to_template():
    def boom(system, facts):
        raise RuntimeError("provider down")

    narrative = agent.write_narrative(_report(), llm=boom)
    assert narrative["source"] == "template" and "failed" in narrative["note"]


def test_template_and_prompt_wording_contain_no_advice():
    facts = agent.render_facts(_report())
    assert agent.advice_violations(facts) == []
    assert ADVISER_NOTE in facts
    assert "regulated financial adviser" in ADVISER_NOTE
    assert "Never recommend" in agent.SYSTEM_PROMPT


def test_unsupported_numbers_accepts_whole_unit_rounding():
    facts = "Income £8,700.25 a year in 95% of windows."
    assert agent.unsupported_numbers("About £8,700 a year in 95% of windows.", facts) == []
    assert agent.unsupported_numbers("About £9,000 a year.", facts) == [9000.0]
