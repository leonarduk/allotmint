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
