from mcp.types import Tool

from backend.chat.local_tools import NAVIGATE_TOOL_NAME, ChatPage, LocalTools, merge_tool_lists

PAGES = [ChatPage("/transactions", "Transactions"), ChatPage("/market", "Market")]


def test_no_pages_means_no_navigate_tool():
    local = LocalTools()
    assert local.tools() == []
    assert not local.handles(NAVIGATE_TOOL_NAME)


def test_navigate_tool_path_is_limited_to_the_given_pages():
    (tool,) = LocalTools(pages=PAGES).tools()
    assert tool.name == NAVIGATE_TOOL_NAME
    assert tool.input_schema["properties"]["path"]["enum"] == ["/transactions", "/market"]
    assert "/transactions (Transactions)" in tool.description


def test_navigate_records_a_known_page():
    local = LocalTools(pages=PAGES)
    text, is_error = local.call(NAVIGATE_TOOL_NAME, {"path": "/market"})
    assert not is_error
    assert "Market" in text
    assert local.navigate_to == "/market"


def test_navigate_rejects_an_unknown_page():
    local = LocalTools(pages=PAGES)
    text, is_error = local.call(NAVIGATE_TOOL_NAME, {"path": "https://evil.example.com"})
    assert is_error
    assert "/transactions" in text
    assert local.navigate_to is None


def test_merge_tool_lists_lets_local_tool_replace_same_named_mcp_tool():
    mcp_tools = [
        Tool(name="get_portfolio", input_schema={"type": "object"}),
        Tool(name=NAVIGATE_TOOL_NAME, input_schema={"type": "object"}),
    ]
    merged = merge_tool_lists(mcp_tools, LocalTools(pages=PAGES))
    assert [tool.name for tool in merged] == ["get_portfolio", NAVIGATE_TOOL_NAME]
    assert merged[1].input_schema["properties"]["path"]["enum"] == ["/transactions", "/market"]


def test_merge_tool_lists_without_local_tools_returns_mcp_tools():
    mcp_tools = [Tool(name="get_portfolio", input_schema={"type": "object"})]
    assert merge_tool_lists(mcp_tools, None) == mcp_tools


def test_system_prompt_from_context_names_the_page_and_ticker():
    from backend.chat.local_tools import system_prompt_from_context

    assert system_prompt_from_context(None) is None
    assert "/transactions" in system_prompt_from_context({"path": "/transactions", "ticker": None})
    prompt = system_prompt_from_context({"path": "/research/ARG.TO", "ticker": "ARG.TO"})
    assert "/research/ARG.TO" in prompt and "this stock" in prompt


def test_build_system_prompt_always_carries_the_base_guidance():
    from backend.chat.local_tools import BASE_SYSTEM_PROMPT, build_system_prompt

    assert build_system_prompt(None) == BASE_SYSTEM_PROMPT
    prompt = build_system_prompt({"path": "/research/ARG.TO", "ticker": "ARG.TO"})
    assert prompt.startswith(BASE_SYSTEM_PROMPT)
    assert prompt.endswith('treat "this stock" or "this" as ARG.TO.')


def test_base_system_prompt_stops_the_model_denying_data_it_has_no_tool_for():
    # #8685: the assistant said AllotMint had "no P/E, P/B, yield" data.
    from backend.chat.local_tools import BASE_SYSTEM_PROMPT

    assert "P/E" in BASE_SYSTEM_PROMPT and "dividend yield" in BASE_SYSTEM_PROMPT
    assert "do not claim AllotMint has no such data" in BASE_SYSTEM_PROMPT
    assert "source" in BASE_SYSTEM_PROMPT and "as-of date" in BASE_SYSTEM_PROMPT


def test_base_system_prompt_carries_the_portfolio_review_playbook():
    # #9125: every provider gets the review steps, so the playbook is not tied to one model.
    from backend.chat.local_tools import (
        BASE_SYSTEM_PROMPT,
        CORE_SYSTEM_PROMPT,
        PORTFOLIO_REVIEW_GUIDANCE,
    )

    assert BASE_SYSTEM_PROMPT.startswith(CORE_SYSTEM_PROMPT)
    assert BASE_SYSTEM_PROMPT.endswith(PORTFOLIO_REVIEW_GUIDANCE)
    for step in ("Holdings", "Screens", "News", "Constraints"):
        assert step in PORTFOLIO_REVIEW_GUIDANCE
    for heading in (
        "Snapshot",
        "What stands out",
        "Options to consider",
        "What to watch",
        "Data caveats",
    ):
        assert heading in PORTFOLIO_REVIEW_GUIDANCE


def test_review_playbook_is_decision_support_not_advice():
    from backend.chat.local_tools import PORTFOLIO_REVIEW_GUIDANCE

    assert "not personal recommendations" in PORTFOLIO_REVIEW_GUIDANCE
    assert "do not tell the user to buy or sell" in PORTFOLIO_REVIEW_GUIDANCE
    assert "not a regulated financial adviser" in PORTFOLIO_REVIEW_GUIDANCE
    # Missing data is reported, never assumed; steps name capabilities, not tool names.
    assert "do not assume" in PORTFOLIO_REVIEW_GUIDANCE
    assert "say which steps you could not do" in PORTFOLIO_REVIEW_GUIDANCE
    assert "screen_portfolio" not in PORTFOLIO_REVIEW_GUIDANCE
