"""Look-through factsheet agent (#10492): mocked LLM and web, synthetic factsheet only."""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.common import instruments, look_through
from backend.fund_upkeep import bot, charges_agent, look_through_agent, proposals
from tests.backend.fund_upkeep.fixtures import stored_meta
from tests.backend.fund_upkeep.test_charges_agent import GOOD_ANSWER, FakeResponse, _tool_call, scripted_llm

TODAY = date(2026, 10, 9)
SEARCH_URL = charges_agent.BRAVE_SEARCH_URL
FACTSHEET_URL = "https://issuer.example.com/docs/fundx-factsheet.html"
OTHER_URL = "https://elsewhere.example.com/other-factsheet.html"
# Synthetic issuer factsheet; not copied from any real document.
FACTSHEET_HTML = b"""<html><body>
<h1>Example Global Fund - Monthly Factsheet</h1>
<p>ISIN GB00EXAMPLE1. Data as at 31 August 2026.</p>
<h2>Country allocation</h2>
<table><tr><td>Exampleland</td><td>55.0%</td></tr><tr><td>Samplestan</td><td>30.0%</td></tr>
<tr><td>Testonia</td><td>15.0%</td></tr></table>
<h2>Sector allocation</h2>
<table><tr><td>Technology</td><td>40.0%</td></tr><tr><td>Financials</td><td>35.0%</td></tr>
<tr><td>Industrials</td><td>25.0%</td></tr></table>
<h2>Top holdings</h2>
<table><tr><td>Example Widgets plc</td><td>6.0%</td></tr><tr><td>Sample Bank SA</td><td>4.5%</td></tr></table>
</body></html>"""

FUND = {"ticker": "FUNDX.L", "name": "Example Global Fund", "isin": "GB00EXAMPLE1"}
BLOCK = {
    "countries": {"Exampleland": 55.0, "Samplestan": 30.0, "Testonia": 15.0},
    "sectors": {"Technology": 40.0, "Financials": 35.0, "Industrials": 25.0},
    "top_holdings": [
        {"name": "Example Widgets plc", "isin": "XS0000000017", "weight_pct": 6.0},
        {"name": "Sample Bank SA", "isin": None, "weight_pct": 4.5},
    ],
}
GOOD_LT_ANSWER = {
    "look_through": BLOCK,
    "source_url": FACTSHEET_URL,
    "document_date": "2026-08-31",
    "confidence": "high",
}


class FactsheetSession:
    """Serves search results and the synthetic factsheet; records every request."""

    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url == SEARCH_URL:
            results = [{"title": "Example Global Fund factsheet", "url": FACTSHEET_URL, "description": "Factsheet"}]
            return FakeResponse(payload={"web": {"results": results}})
        return FakeResponse(FACTSHEET_HTML, url=url)


def factsheet_llm(final_answer):
    """An LLM that searches, fetches the factsheet, then answers ``final_answer``."""
    script = [
        {"content": "", "tool_calls": [_tool_call("1", "search_web", query="GB00EXAMPLE1 factsheet")]},
        {"content": "", "tool_calls": [_tool_call("2", "fetch_document", url=FACTSHEET_URL)]},
        {"content": json.dumps(final_answer)},
    ]
    seen = []

    def step(messages, tools):
        seen.append({"messages": [dict(m) for m in messages], "tools": tools})
        return script[len(seen) - 1]

    step.seen = seen
    return step


def routed_llm(charges, look_through_step):
    """One configured LLM serving both agents, routed by their system prompts."""

    def step(messages, tools):
        target = look_through_step if messages[0]["content"] == look_through_agent.SYSTEM_PROMPT else charges
        return target(messages, tools)

    return step


@pytest.fixture
def toolbox(catalogue):
    return charges_agent.ReadOnlyToolbox(session=FactsheetSession(), brave_api_key="test-key")


def test_mocked_factsheet_produces_a_usable_sourced_block(toolbox):
    llm = factsheet_llm(GOOD_LT_ANSWER)

    outcome = look_through_agent.propose_look_through(FUND, llm=llm, toolbox=toolbox, today=TODAY)

    assert outcome["status"] == "proposed"
    proposal = outcome["proposal"]
    assert proposal["kind"] == proposals.KIND_LOOK_THROUGH
    assert proposal["ticker"] == "FUNDX.L"
    assert proposal["source_url"] == FACTSHEET_URL
    assert proposal["document_date"] == "2026-08-31"
    value = proposal["value"]
    assert look_through.usable_look_through({"look_through": value}) is value
    assert value["countries"] == BLOCK["countries"]
    assert value["sectors"] == BLOCK["sectors"]
    assert value["top_holdings"] == BLOCK["top_holdings"]
    assert (value["source"], value["source_url"], value["as_of"], value["fetched"]) == (
        "issuer factsheet",
        FACTSHEET_URL,
        "2026-08-31",
        "2026-10-09",
    )
    # The factsheet reached the model as text, and only read-only tools were offered.
    tool_texts = [m["content"] for m in llm.seen[-1]["messages"] if m["role"] == "tool"]
    assert any("Exampleland 55.0%" in text for text in tool_texts)
    assert all({t["function"]["name"] for t in s["tools"]} == charges_agent.READ_ONLY_TOOLS for s in llm.seen)
    assert llm.seen[0]["messages"][0]["content"] == look_through_agent.SYSTEM_PROMPT


def test_model_supplied_provenance_and_bad_weights_are_dropped(toolbox):
    block = {
        **BLOCK,
        "countries": {**BLOCK["countries"], "Nowhere": "lots", "Overflow": 250.0, "Negative": -1.0},
        "top_holdings": [*BLOCK["top_holdings"], {"name": "", "weight_pct": 1.0}, {"name": "No weight"}],
        "source": "made up",
        "source_url": OTHER_URL,
        "as_of": "2020-01-01",
        "fetched": "2020-01-01",
    }

    outcome = look_through_agent.propose_look_through(
        FUND, llm=factsheet_llm({**GOOD_LT_ANSWER, "look_through": block}), toolbox=toolbox, today=TODAY
    )

    value = outcome["proposal"]["value"]
    assert value["countries"] == BLOCK["countries"]
    assert value["top_holdings"] == BLOCK["top_holdings"]
    assert (value["source"], value["source_url"], value["as_of"]) == ("issuer factsheet", FACTSHEET_URL, "2026-08-31")


@pytest.mark.parametrize("missing", ["countries", "sectors"])
def test_block_without_country_or_sector_weights_is_rejected(toolbox, missing):
    block = {k: v for k, v in BLOCK.items() if k != missing}

    outcome = look_through_agent.propose_look_through(
        FUND, llm=factsheet_llm({**GOOD_LT_ANSWER, "look_through": block}), toolbox=toolbox, today=TODAY
    )

    assert outcome == {"status": "rejected", "reason": proposals.REJECTION_REASONS["look_through_weights"]}


def test_block_citing_a_source_never_fetched_is_rejected(toolbox):
    outcome = look_through_agent.propose_look_through(
        FUND, llm=factsheet_llm({**GOOD_LT_ANSWER, "source_url": OTHER_URL}), toolbox=toolbox, today=TODAY
    )

    assert outcome == {"status": "rejected", "reason": proposals.REJECTION_REASONS["unfetched_source"]}


def test_block_without_a_document_date_is_rejected(toolbox):
    answer = {k: v for k, v in GOOD_LT_ANSWER.items() if k != "document_date"}

    outcome = look_through_agent.propose_look_through(FUND, llm=factsheet_llm(answer), toolbox=toolbox, today=TODAY)

    assert outcome == {"status": "rejected", "reason": proposals.REJECTION_REASONS["document_date"]}


def test_not_found_answer_is_reported(toolbox):
    outcome = look_through_agent.propose_look_through(
        FUND, llm=factsheet_llm({"not_found": "no breakdown published"}), toolbox=toolbox, today=TODAY
    )

    assert outcome == {"status": "not_found", "reason": "no breakdown published"}


@pytest.fixture
def stub_exposure(monkeypatch):
    # The real compute_look_through builds a process-wide securities cache (see test_look_through_upkeep.py).
    monkeypatch.setattr(bot, "compute_look_through", lambda _portfolio: {"total_value_gbp": 0.0, "holdings": []})


PORTFOLIO = {"accounts": [{"account_type": "ISA", "holdings": [{"ticker": "FUNDX.L", "market_value_gbp": 1000.0}]}]}


def _run(llm, toolbox, refresh, **kwargs):
    return bot.run(
        owner="alex",
        portfolio=PORTFOLIO,
        transactions=[],
        today=TODAY,
        llm=llm,
        toolbox=toolbox,
        refresh_kwargs={"refresh": refresh, "sleep": lambda _s: None},
        **kwargs,
    )


@pytest.mark.usefixtures("stub_exposure")
def test_run_queues_a_look_through_proposal_and_approval_makes_the_fund_looked_through(catalogue, toolbox, monkeypatch):
    before = stored_meta(catalogue)
    llm = routed_llm(scripted_llm({"not_found": "no KIID"}), factsheet_llm(GOOD_LT_ANSWER))

    result = _run(llm, toolbox, lambda _t: {"updated": False})

    assert result["look_through"]["unresolved"] == [{"ticker": "FUNDX.L", "reason": "no source"}]
    [outcome] = result["look_through_proposals"]
    assert outcome["ticker"] == "FUNDX.L" and outcome["status"] == "queued"
    # Proposals only: nothing is written before approval.
    assert stored_meta(catalogue) == before
    [pending] = proposals.list_proposals("pending")
    assert pending["id"] == outcome["proposal_id"]
    assert look_through.usable_look_through({"look_through": pending["value"]}) is not None

    proposals.approve(pending["id"], actor="alex")

    meta = stored_meta(catalogue)
    assert meta["look_through"]["source_url"] == FACTSHEET_URL
    assert meta["name"] == "Example Global Fund"  # merge, not replace
    monkeypatch.setattr(look_through, "get_instrument_meta", instruments.get_instrument_meta)
    row = {"ticker": "FUNDX.L", "name": "Example Global Fund", "market_value_gbp": 1000.0}
    monkeypatch.setattr(look_through, "aggregate_by_ticker", lambda _p: [row])
    exposure = look_through.compute_look_through(PORTFOLIO)
    assert exposure["coverage"]["looked_through_value_gbp"] == 1000.0
    assert exposure["coverage"]["not_covered"] == []
    assert {c["label"] for c in exposure["countries"]} == set(BLOCK["countries"])


@pytest.mark.usefixtures("stub_exposure")
def test_a_fresh_fund_is_neither_refetched_nor_sent_to_the_agent(catalogue, toolbox):
    def must_not_ask(_messages, _tools):
        raise AssertionError("agent asked about a fresh fund")

    fresh = {"ongoing_charge_pct": 0.2, "look_through": {"fetched": "2026-10-01"}}
    instruments.save_instrument_meta("FUNDX.L", {**instruments.get_instrument_meta("FUNDX.L"), **fresh})
    instruments.get_instrument_meta.cache_clear()

    result = _run(must_not_ask, toolbox, lambda _t: pytest.fail("fresh block refetched"))

    assert result["look_through"]["fresh"] == [{"ticker": "FUNDX.L"}]
    assert result["look_through_proposals"] == []
    assert proposals.list_proposals() == []


def test_only_funds_without_a_source_go_to_the_agent():
    funds = [{"ticker": t} for t in ("NOSRC.L", "NOISIN.L", "FAILED.L", "FRESH.L")]
    refresh = {
        "fresh": [{"ticker": "FRESH.L"}],
        "unresolved": [{"ticker": "NOSRC.L", "reason": "no source"}, {"ticker": "NOISIN.L", "reason": "no ISIN"}],
        "failed": [{"ticker": "FAILED.L", "reason": "source request failed"}],
    }

    assert bot._without_source(funds, refresh) == [{"ticker": "NOSRC.L"}]
    assert bot._without_source(funds, {"skipped": "offline"}) == []


@pytest.mark.usefixtures("stub_exposure")
def test_run_without_llm_lists_the_unresolved_funds_and_queues_nothing(catalogue, toolbox):
    result = _run(None, toolbox, lambda _t: {"updated": False})

    assert result["look_through_proposals"] == {"skipped": "no LLM configured", "funds": ["FUNDX.L"]}
    assert proposals.list_proposals() == []


@pytest.mark.usefixtures("stub_exposure")
def test_agent_funds_are_capped_per_run(catalogue, toolbox):
    llm = routed_llm(scripted_llm(GOOD_ANSWER), factsheet_llm(GOOD_LT_ANSWER))

    result = _run(llm, toolbox, lambda _t: {"updated": False}, max_agent_funds=0)

    assert result["ongoing_charges"] == []
    assert result["look_through_proposals"] == []
