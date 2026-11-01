"""LLM explanations of unmatched contributions (#10491): read-only allowlist, no advice, mocked models only."""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from backend.allowance_guardian import agent, report
from backend.allowance_guardian.schedule import ScheduledContribution
from backend.chat import bedrock_agent, openai_compat_agent, providers, tool_switches
from backend.common.advice_wording import advice_phrases
from backend.routes.transactions import Transaction

TODAY = date(2026, 8, 20)
MCP_URL = "https://mcp.example.test/mcp"
WRITE_VERBS = ("set", "save", "update", "delete", "add", "create", "write", "approve", "refresh", "import", "record")
# A synthetic MCP toolset: the allowlist plus write tools and other reads the explainer must not see.
MCP_TOOLSET = [
    "get_transactions",
    "summarise_transactions",
    "get_pension_forecast",
    "get_portfolio",
    "add_transaction",
    "save_contribution_schedule",
    "delete_transaction",
    "create_github_issue",
]


def _schedule() -> list[ScheduledContribution]:
    return [
        ScheduledContribution(
            account="isa", amount_minor=50_000, source="isa_subscription", expected_day=1, start_date="2026-05-01"
        )
    ]


def _tx(day: str, amount_minor: int) -> Transaction:
    return Transaction(
        owner="alex",
        account="isa",
        id=f"isa-{day}-{amount_minor}",
        type="DEPOSIT",
        date=day,
        amount_minor=amount_minor,
        currency="GBP",
        comments="Subscription",
    )


def _transactions() -> list[Transaction]:
    # 1 May and 1 Aug on time; June missing (£500 arrived on 25 June, after the window);
    # July a different amount (£200 + £150 = £350 against £500).
    return [
        _tx("2026-05-01", 50_000),
        _tx("2026-06-25", 50_000),
        _tx("2026-07-01", 20_000),
        _tx("2026-07-03", 15_000),
        _tx("2026-08-01", 50_000),
    ]


def _report(**kwargs) -> dict:
    defaults = {"today": TODAY, "transactions": _transactions(), "schedule": _schedule(), "allowances": None}
    return report.run("alex", **{**defaults, **kwargs})


def _reply(*explanations: str) -> str:
    items = [{"id": index, "explanation": text} for index, text in enumerate(explanations)]
    return json.dumps({"explanations": items})


GOOD_REPLY = _reply(
    "No deposit arrived between 27 May and 15 June; a payment of £500.00 arrived on 2026-06-25, "
    "24 days after the expected date.",
    "Two payments in the window, £200.00 and £150.00, add up to £350.00, which is £150.00 less than expected.",
)


class FakeChatTurn:
    """Records each call; returns ``reply`` (or raises it when it is an exception)."""

    def __init__(self, reply, tool_log=()):
        self.reply = reply
        self.tool_log = list(tool_log)
        self.calls: list[dict] = []

    async def __call__(self, message, history, **kwargs):
        self.calls.append({"message": message, "history": history, **kwargs})
        kwargs["limits"].tool_log.extend(self.tool_log)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _explain(reply, **kwargs):
    turn = FakeChatTurn(reply, **kwargs)
    cfg = SimpleNamespace(mcp_server_url=MCP_URL)
    return agent.explain_unmatched(_report(), "alex", chat_turn=turn, cfg=cfg), turn


# --- the allowlist ---------------------------------------------------------------------------


def test_allowlist_is_exactly_the_read_only_tools():
    assert agent.READ_ONLY_TOOLS == {"get_transactions", "summarise_transactions", "get_pension_forecast"}
    for name in agent.READ_ONLY_TOOLS:
        assert tool_switches.is_read_only_tool_name(name), name
        assert not any(verb in name.split("_") for verb in WRITE_VERBS), name


def test_explainer_passes_only_the_allowlist_to_the_provider():
    _, turn = _explain(GOOD_REPLY)

    [call] = turn.calls
    limits = call["limits"]
    assert limits.allowed_tools == agent.READ_ONLY_TOOLS
    assert limits.max_iterations == agent.MAX_TOOL_CALL_ROUNDS
    assert limits.max_tokens == agent.MAX_OUTPUT_TOKENS
    assert call["system_prompt"] == agent.SYSTEM_PROMPT
    assert call["mcp_server_url"] == MCP_URL
    assert call["history"] == []
    for name in MCP_TOOLSET:
        assert limits.allows(name) == (name in agent.READ_ONLY_TOOLS), name


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
        text = json.dumps([{"date": "2026-06-25", "amount_minor": 50000, "account": "isa"}])
        return SimpleNamespace(content=[SimpleNamespace(text=text)], is_error=False)


def _patch_mcp(monkeypatch, module) -> FakeSession:
    session = FakeSession()

    @asynccontextmanager
    async def fake_mcp_session(url):
        assert url == MCP_URL
        yield session

    monkeypatch.setattr(module, "mcp_session", fake_mcp_session)
    return session


def _explain_through_provider(cfg) -> list[dict]:
    """explain_unmatched through the real provider seam (``run_configured_chat_turn``)."""
    return agent.explain_unmatched(_report(), "alex", chat_turn=providers.run_configured_chat_turn, cfg=cfg)


def _bedrock_tool_use(tool_id, name):
    content = [{"toolUse": {"toolUseId": tool_id, "name": name, "input": {"owner": "alex"}}}]
    return {"output": {"message": {"role": "assistant", "content": content}}}


def test_bedrock_offers_only_the_allowlist_and_refuses_a_write_tool(monkeypatch):
    session = _patch_mcp(monkeypatch, bedrock_agent)
    responses = [
        _bedrock_tool_use("t1", "get_transactions"),
        _bedrock_tool_use("t2", "add_transaction"),
        {"output": {"message": {"role": "assistant", "content": [{"text": GOOD_REPLY}]}}},
    ]
    seen = []

    class FakeBedrock:
        def converse(self, **kwargs):
            seen.append(copy.deepcopy(kwargs))
            return responses[len(seen) - 1]

    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: FakeBedrock())
    cfg = SimpleNamespace(chat_provider="bedrock", app_env="aws", bedrock_model_id="test-model", mcp_server_url=MCP_URL)

    entries = _explain_through_provider(cfg)

    for request in seen:
        offered = {tool["toolSpec"]["name"] for tool in request["toolConfig"]["tools"]}
        assert offered == agent.READ_ONLY_TOOLS
    assert [name for name, _ in session.calls] == ["get_transactions"]
    assert [entry["explanation"] is not None for entry in entries] == [True, True]


def _openai_tool_call(call_id, name):
    call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": '{"owner": "alex"}'}}
    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [call]}}]}


def test_openai_compatible_offers_only_the_allowlist_and_refuses_a_write_tool(monkeypatch):
    session = _patch_mcp(monkeypatch, openai_compat_agent)
    responses = [
        _openai_tool_call("c1", "summarise_transactions"),
        _openai_tool_call("c2", "save_contribution_schedule"),
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

    entries = _explain_through_provider(cfg)

    for body in bodies:
        assert {tool["function"]["name"] for tool in body["tools"]} == agent.READ_ONLY_TOOLS
        assert body["max_tokens"] == agent.MAX_OUTPUT_TOKENS
    assert [name for name, _ in session.calls] == ["summarise_transactions"]
    assert [entry["explanation"] is not None for entry in entries] == [True, True]


# --- explanations ----------------------------------------------------------------------------


def test_missing_and_wrong_amount_each_get_one_explanation():
    entries, turn = _explain(GOOD_REPLY)

    assert [(e["expected_date"], e["account"], e["status"]) for e in entries] == [
        ("2026-06-01", "isa", "missing"),
        ("2026-07-01", "isa", "wrong_amount"),
    ]
    assert all(e["explanation"] and e["note"] is None for e in entries)
    assert "arrived on 2026-06-25" in entries[0]["explanation"]
    assert "£350.00" in entries[1]["explanation"]
    message = turn.calls[0]["message"]
    assert "Owner: alex." in message
    assert "2026-06-25 £500.00 (24 days after the expected date)" in message
    assert "Nearest deposit in the window: 2026-07-01 £200.00, £300.00 less than expected" in message
    assert "2026-07-01 £200.00, 2026-07-03 £150.00; together £350.00, £150.00 less than expected" in message


def test_late_contribution_is_explained_with_its_days_late():
    transactions = [_tx("2026-05-01", 50_000), _tx("2026-06-10", 50_000)]
    report_ = _report(transactions=transactions, today=date(2026, 6, 12))
    turn = FakeChatTurn(_reply("The payment of £500.00 arrived on 2026-06-10, 9 days after the expected date."))

    entries = agent.explain_unmatched(report_, "alex", chat_turn=turn, cfg=SimpleNamespace(mcp_server_url=MCP_URL))

    assert [(e["status"], e["note"]) for e in entries] == [("late", None)]
    assert "9 days after the expected date" in turn.calls[0]["message"]


def test_nothing_unmatched_makes_no_model_call():
    transactions = [_tx("2026-05-01", 50_000)]
    report_ = _report(transactions=transactions, today=date(2026, 5, 3))
    turn = FakeChatTurn(GOOD_REPLY)

    assert agent.explain_unmatched(report_, "alex", chat_turn=turn, cfg=SimpleNamespace(mcp_server_url=MCP_URL)) == []
    assert turn.calls == []


@pytest.mark.parametrize(
    "advice",
    [
        "The payment was missed; you should pay £500.00 now.",
        "Consider increasing your monthly payment.",
        "We recommend checking with the provider.",
        "Make sure the standing order is set up.",
        "Contribute £150.00 more before April.",
    ],
)
def test_advice_wording_is_rejected(advice):
    entries, _ = _explain(_reply(advice, "Two payments add up to £350.00."))

    assert entries[0]["explanation"] is None
    assert entries[0]["note"] == agent.NOTE_ADVICE
    assert entries[1]["explanation"] == "Two payments add up to £350.00."


def test_every_kept_explanation_passes_the_advice_check():
    entries, _ = _explain(GOOD_REPLY)

    assert not advice_phrases(" ".join(e["explanation"] for e in entries))


def test_an_amount_not_in_the_records_is_rejected():
    entries, _ = _explain(_reply("A payment of £475.00 arrived late.", "Two payments add up to £350.00."))

    assert (entries[0]["explanation"], entries[0]["note"]) == (None, agent.NOTE_FIGURES)
    assert entries[1]["note"] is None


def test_an_amount_from_a_tool_result_this_run_is_accepted():
    tool_log = [{"tool": "get_transactions", "result": '[{"amount_minor": 47500}]', "is_error": False}]
    entries, _ = _explain(_reply("A deposit of £475.00 is recorded in June.", ""), tool_log=tool_log)

    assert entries[0]["explanation"] == "A deposit of £475.00 is recorded in June."
    assert (entries[1]["explanation"], entries[1]["note"]) == (None, agent.NOTE_NO_REPLY)


@pytest.mark.parametrize(
    "invented", ["£25.00", "£24.00", "£2,026.00", "£6.00"], ids=["day", "days-late", "year", "month"]
)
def test_an_amount_equal_to_a_date_part_or_day_count_in_the_facts_is_rejected(invented):
    # The facts mention 2026-06-25 and "24 days after"; those numbers are not £ amounts.
    entries, _ = _explain(_reply(f"A payment of {invented} arrived late.", "Two payments add up to £350.00."))

    assert (entries[0]["explanation"], entries[0]["note"]) == (None, agent.NOTE_FIGURES)
    assert entries[1]["note"] is None


def test_an_amount_minor_field_nested_in_a_json_tool_result_is_accepted():
    result = json.dumps({"tax_year": "2026-27", "transactions": [{"date": "2026-06-12", "amount_minor": 12_345}]})
    tool_log = [{"tool": "get_transactions", "result": result, "is_error": False}]
    entries, _ = _explain(_reply("A deposit of £123.45 is recorded on 2026-06-12.", ""), tool_log=tool_log)

    assert entries[0]["explanation"] == "A deposit of £123.45 is recorded on 2026-06-12."


def test_non_money_numbers_in_a_json_tool_result_are_not_amounts():
    result = json.dumps({"count": 47, "days": 61, "transactions": [{"date": "2026-06-12", "amount": 10}]})
    tool_log = [{"tool": "get_transactions", "result": result, "is_error": False}]
    entries, _ = _explain(_reply("A payment of £61.00 arrived.", "A payment of £10.00 arrived."), tool_log=tool_log)

    assert (entries[0]["explanation"], entries[0]["note"]) == (None, agent.NOTE_FIGURES)
    assert entries[1]["note"] is None


def test_a_non_json_tool_result_supplies_only_its_pound_amounts():
    tool_log = [{"tool": "summarise_transactions", "result": "12 deposits, total £640.50", "is_error": False}]
    entries, _ = _explain(_reply("Deposits total £640.50.", "There were £12.00 of deposits."), tool_log=tool_log)

    assert entries[0]["explanation"] == "Deposits total £640.50."
    assert (entries[1]["explanation"], entries[1]["note"]) == (None, agent.NOTE_FIGURES)


def test_a_whole_pound_amount_matches_its_pence_form():
    # The facts say £500.00; the model may quote it as £500.
    entries, _ = _explain(_reply("A payment of £500 arrived on 2026-06-25.", "Two payments add up to £350."))

    assert [e["note"] for e in entries] == [None, None]


def test_an_unparseable_reply_leaves_every_entry_unexplained():
    entries, _ = _explain("I could not work it out.")

    assert [(e["explanation"], e["note"]) for e in entries] == [(None, agent.NOTE_NO_REPLY)] * 2


def test_a_long_explanation_is_truncated():
    entries, _ = _explain(_reply("No deposit arrived. " * 40, ""))

    assert len(entries[0]["explanation"]) == agent.MAX_EXPLANATION_CHARS


def test_a_provider_failure_is_a_note_not_an_error():
    entries, _ = _explain(RuntimeError("provider down"))

    assert [(e["explanation"], e["note"]) for e in entries] == [(None, agent.NOTE_FAILED)] * 2


def test_without_an_mcp_server_nothing_is_called():
    turn = FakeChatTurn(GOOD_REPLY)

    entries = agent.explain_unmatched(_report(), "alex", chat_turn=turn, cfg=SimpleNamespace(mcp_server_url=None))

    assert [e["note"] for e in entries] == [agent.NOTE_NOT_CONFIGURED] * 2
    assert turn.calls == []


async def test_inside_a_running_event_loop_it_falls_back_with_a_note():
    entries, turn = _explain(GOOD_REPLY)

    assert [e["note"] for e in entries] == [agent.NOTE_FAILED] * 2
    assert turn.calls == []


# --- report.run ------------------------------------------------------------------------------


def test_report_is_deterministic_by_default(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the explainer must not run unless asked")

    monkeypatch.setattr(agent, "explain_unmatched", boom)

    assert "explanations" not in _report()


def test_report_explain_adds_the_explanations(monkeypatch):
    seen = {}

    def fake_explain(result, owner):
        seen.update(owner=owner, counts=result["contributions"]["counts"])
        return [{"expected_date": "2026-06-01", "account": "isa", "explanation": "x"}]

    monkeypatch.setattr(agent, "explain_unmatched", fake_explain)

    result = _report(explain=True)

    assert result["explanations"] == [{"expected_date": "2026-06-01", "account": "isa", "explanation": "x"}]
    assert seen == {"owner": "alex", "counts": {**seen["counts"], "missing": 1, "wrong_amount": 1}}
