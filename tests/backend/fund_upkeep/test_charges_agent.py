"""OCF finder agent (#10482): mocked LLM and web, synthetic factsheet only."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from backend.fund_upkeep import charges_agent, proposals

TODAY = date(2026, 10, 9)
DOC_URL = "https://issuer.example.com/docs/fundx-kiid.html"
# Synthetic issuer factsheet; not copied from any real document.
FACTSHEET_HTML = b"""<html><head><script>var x = 1;</script></head><body>
<h1>Example Global Fund - Key Information Document</h1>
<p>ISIN GB00EXAMPLE1. Document date: 1 September 2026.</p>
<table><tr><td>Ongoing charges</td><td>0.22%</td></tr></table>
</body></html>"""


class FakeResponse:
    def __init__(self, content=b"", url="", content_type="text/html", payload=None):
        self.content = content
        self.url = url
        self.headers = {"Content-Type": content_type}
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    """Serves the synthetic factsheet and search results; records every request."""

    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url == charges_agent.BRAVE_SEARCH_URL:
            results = [{"title": "Example Global Fund KIID", "url": DOC_URL, "description": "KIID"}]
            return FakeResponse(payload={"web": {"results": results}})
        return FakeResponse(FACTSHEET_HTML, url=url)


def _tool_call(call_id, name, **arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def scripted_llm(final_answer):
    """An LLM that searches, fetches the factsheet, then answers ``final_answer``."""
    script = [
        {"content": "", "tool_calls": [_tool_call("1", "get_instrument", ticker="FUNDX.L")]},
        {"content": "", "tool_calls": [_tool_call("2", "search_web", query="GB00EXAMPLE1 KIID")]},
        {"content": "", "tool_calls": [_tool_call("3", "fetch_document", url=DOC_URL)]},
        {"content": json.dumps(final_answer)},
    ]
    seen = []

    def step(messages, tools):
        seen.append({"messages": [dict(m) for m in messages], "tools": tools})
        return script[len(seen) - 1]

    step.seen = seen
    return step


FUND = {"ticker": "FUNDX.L", "name": "Example Global Fund", "isin": "GB00EXAMPLE1"}
GOOD_ANSWER = {"ongoing_charge_pct": 0.22, "source_url": DOC_URL, "document_date": "2026-09-01", "confidence": "high"}


@pytest.fixture
def toolbox(catalogue):
    return charges_agent.ReadOnlyToolbox(session=FakeSession(), brave_api_key="test-key")


def test_tool_allowlist_contains_no_write_tools():
    names = {spec["function"]["name"] for spec in charges_agent.TOOL_SPECS}
    assert (
        names == charges_agent.READ_ONLY_TOOLS == {"get_instrument", "get_fund_facts", "search_web", "fetch_document"}
    )
    write_words = re.compile(r"(save|write|update|create|delete|set|put|post|approve|refresh)", re.IGNORECASE)
    assert not [n for n in names if write_words.search(n)]


def test_toolbox_refuses_any_tool_outside_the_allowlist(toolbox):
    with pytest.raises(ValueError, match="not allowed"):
        toolbox.call("save_instrument_meta", {"ticker": "FUNDX.L"})


def test_mocked_factsheet_produces_sourced_proposal(toolbox):
    llm = scripted_llm(GOOD_ANSWER)

    outcome = charges_agent.propose_charge(FUND, llm=llm, toolbox=toolbox, today=TODAY)

    assert outcome["status"] == "proposed"
    proposal = outcome["proposal"]
    assert proposal["value"] == 0.22
    assert proposal["source_url"] == DOC_URL
    assert proposal["document_date"] == "2026-09-01"
    # The fetched page reached the model as plain text with scripts stripped.
    tool_texts = [m["content"] for m in llm.seen[-1]["messages"] if m["role"] == "tool"]
    assert any("Ongoing charges 0.22%" in text and "var x" not in text for text in tool_texts)
    # Every offered tool list is the read-only allowlist.
    assert all({t["function"]["name"] for t in s["tools"]} == charges_agent.READ_ONLY_TOOLS for s in llm.seen)


def test_typed_22_for_022_is_rejected_by_plausibility_cap(toolbox):
    outcome = charges_agent.propose_charge(
        FUND, llm=scripted_llm({**GOOD_ANSWER, "ongoing_charge_pct": 22}), toolbox=toolbox, today=TODAY
    )

    assert outcome["status"] == "rejected"
    assert "plausible" in outcome["reason"]


def test_source_the_agent_never_fetched_is_rejected(toolbox):
    answer = {**GOOD_ANSWER, "source_url": "https://elsewhere.example.com/other.pdf"}

    outcome = charges_agent.propose_charge(FUND, llm=scripted_llm(answer), toolbox=toolbox, today=TODAY)

    assert outcome == {"status": "rejected", "reason": "the cited source was not fetched during this run"}


def test_missing_document_date_is_rejected(toolbox):
    answer = {k: v for k, v in GOOD_ANSWER.items() if k != "document_date"}

    outcome = charges_agent.propose_charge(FUND, llm=scripted_llm(answer), toolbox=toolbox, today=TODAY)

    assert outcome["status"] == "rejected"
    assert "date" in outcome["reason"]


def test_not_found_answer_is_reported(toolbox):
    outcome = charges_agent.propose_charge(
        FUND, llm=scripted_llm({"not_found": "no public KIID"}), toolbox=toolbox, today=TODAY
    )

    assert outcome == {"status": "not_found", "reason": "no public KIID"}


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://10.0.0.5/kiid",
        "file:///etc/passwd",
        "https://u:p@a.example/",
    ],
)
def test_fetch_refuses_non_public_urls(toolbox, url):
    with pytest.raises(ValueError):
        toolbox.fetch_document(url)
    assert toolbox.fetched_urls == set()


def test_search_without_key_is_reported_not_attempted(catalogue):
    session = FakeSession()
    box = charges_agent.ReadOnlyToolbox(session=session, brave_api_key="")

    with pytest.raises(ValueError, match="not configured"):
        box.search_web("anything")
    assert session.calls == []


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({}, True),
        ({"ongoing_charge_pct": 22}, True),
        ({"ongoing_charge_pct": 0.3}, False),  # hand-entered, undated: left alone
        ({"ongoing_charge_pct": 0.3, proposals.CHARGE_SOURCE_KEY: {"document_date": "2026-01-01"}}, False),
        ({"ongoing_charge_pct": 0.3, proposals.CHARGE_SOURCE_KEY: {"document_date": "2025-01-01"}}, True),
        # A malformed source date is treated like an undated value: left alone.
        ({"ongoing_charge_pct": 0.3, proposals.CHARGE_SOURCE_KEY: {"document_date": "not-a-date"}}, False),
    ],
)
def test_needs_charge(meta, expected):
    assert charges_agent.needs_charge(meta, TODAY) is expected


def test_fetch_refuses_a_hostname_that_resolves_to_a_private_address(catalogue, monkeypatch):
    monkeypatch.setattr(charges_agent, "_resolve_host", lambda _host: ["10.1.2.3"])
    session = FakeSession()
    box = charges_agent.ReadOnlyToolbox(session=session, brave_api_key="k")

    with pytest.raises(ValueError, match="public"):
        box.fetch_document("https://intranet.example.com/kiid.pdf")
    assert session.calls == []


def test_fetch_refuses_a_hostname_that_does_not_resolve(toolbox, monkeypatch):
    monkeypatch.setattr(charges_agent, "_resolve_host", lambda _host: [])

    with pytest.raises(ValueError):
        toolbox.fetch_document("https://no-such-host.example.com/kiid.pdf")


def test_look_through_proposal_is_validated_by_the_shared_reader():
    raw = {
        "ticker": "FUNDX.L",
        "source_url": DOC_URL,
        "document_date": "2026-08-31",
        "look_through": {"countries": {"United States": 60.0, "Japan": 40.0}, "sectors": {"Technology": 100.0}},
    }

    proposal = proposals.validate_look_through(raw, today=TODAY)

    assert proposal["value"]["as_of"] == "2026-08-31"
    assert proposal["value"]["source_url"] == DOC_URL
    assert proposal["value"]["fetched"] == "2026-10-09"
    with pytest.raises(proposals.ProposalRejected):
        proposals.validate_look_through({**raw, "look_through": {"countries": {"US": 100.0}}}, today=TODAY)


class FakeConverseClient:
    """A Bedrock Converse client that replays the scripted replies in Converse shape (#10494)."""

    def __init__(self, final_answer):
        self._script = scripted_llm(final_answer)
        self.requests = []

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        reply = self._script([], [])
        blocks = [{"text": reply["content"]}] if reply.get("content") else []
        for call in reply.get("tool_calls") or []:
            function = call["function"]
            tool_use = {"toolUseId": call["id"], "name": function["name"], "input": json.loads(function["arguments"])}
            blocks.append({"toolUse": tool_use})
        return {"output": {"message": {"role": "assistant", "content": blocks}}}


def _cfg(monkeypatch, provider="bedrock"):
    from backend.config import config

    monkeypatch.setattr(config, "chat_provider", provider)
    monkeypatch.setattr(config, "bedrock_model_id", "test-model")
    return config


def test_bedrock_step_produces_the_same_sourced_proposal(toolbox, monkeypatch):
    client = FakeConverseClient(GOOD_ANSWER)
    llm = charges_agent.bedrock_step(_cfg(monkeypatch), client=client)

    outcome = charges_agent.propose_charge(FUND, llm=llm, toolbox=toolbox, today=TODAY)

    assert outcome["status"] == "proposed"
    assert outcome["proposal"]["value"] == 0.22
    assert outcome["proposal"]["source_url"] == DOC_URL
    assert outcome["proposal"]["document_date"] == "2026-09-01"
    assert len(client.requests) == 4
    for request in client.requests:
        assert request["modelId"] == "test-model"
        assert request["system"] == [{"text": charges_agent.SYSTEM_PROMPT}]
        # Only the read-only allowlist is ever offered to Bedrock.
        offered = {tool["toolSpec"]["name"] for tool in request["toolConfig"]["tools"]}
        assert offered == charges_agent.READ_ONLY_TOOLS
    # The fetched factsheet went back to the model as a toolResult on a user turn.
    last = client.requests[-1]["messages"]
    assert [m["role"] for m in last] == ["user", "assistant", "user", "assistant", "user", "assistant", "user"]
    result = last[-1]["content"][0]["toolResult"]
    assert result["toolUseId"] == "3"
    assert "Ongoing charges 0.22%" in result["content"][0]["text"]


def test_bedrock_conversation_groups_parallel_tool_results_into_one_user_turn():
    calls = [_tool_call("a", "get_instrument", ticker="FUNDX.L"), _tool_call("b", "get_fund_facts", ticker="FUNDX.L")]
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "find it"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        {"role": "tool", "tool_call_id": "a", "content": "{}"},
        {"role": "tool", "tool_call_id": "b", "content": "{}"},
    ]

    system, converted = charges_agent._bedrock_conversation(messages)

    assert system == [{"text": "sys"}]
    assert [m["role"] for m in converted] == ["user", "assistant", "user"]
    # An empty assistant text is dropped: Converse rejects blank text blocks.
    assert [b["toolUse"]["toolUseId"] for b in converted[1]["content"]] == ["a", "b"]
    assert converted[1]["content"][0]["toolUse"]["input"] == {"ticker": "FUNDX.L"}
    assert [b["toolResult"]["toolUseId"] for b in converted[2]["content"]] == ["a", "b"]


def test_bedrock_step_is_none_for_other_providers(monkeypatch):
    assert charges_agent.bedrock_step(_cfg(monkeypatch, "ollama")) is None


@pytest.mark.parametrize(("provider", "expect_bedrock"), [("bedrock", True), ("ollama", False)])
def test_configured_step_uses_bedrock_only_for_the_bedrock_provider(monkeypatch, provider, expect_bedrock):
    sentinel = object()
    monkeypatch.setattr(charges_agent, "bedrock_step", lambda _cfg: sentinel)

    step = charges_agent.configured_step(_cfg(monkeypatch, provider))

    assert step is not None
    assert (step is sentinel) is expect_bedrock
