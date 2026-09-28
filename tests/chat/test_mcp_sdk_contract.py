"""Smoke tests against the real, installed ``mcp`` SDK objects.

The chat agents (``bedrock_agent.py``, ``openai_compat_agent.py``) read
``Tool.input_schema`` and ``CallToolResult.is_error`` -- the mcp 2.x
snake_case field names, renamed from mcp 1.x's ``inputSchema``/``isError``
as part of the #8131 migration. All other coverage for those attribute
accesses uses hand-rolled fakes (``FakeTool``/``FakeCallToolResult``), which
only prove the *agent* code reads the field it's told to and can't catch the
installed SDK reverting or never having had that field. These tests
construct the real pydantic models instead, so a future ``mcp`` downgrade
or a wrong field name is caught here rather than by a runtime
``AttributeError`` in Lambda.
"""

from __future__ import annotations

from mcp.types import CallToolResult, TextContent, Tool


def test_real_tool_exposes_snake_case_input_schema():
    tool = Tool(name="list_owners", description="List owners", input_schema={"type": "object", "properties": {}})
    assert tool.input_schema == {"type": "object", "properties": {}}
    assert not hasattr(tool, "inputSchema")


def test_real_call_tool_result_exposes_snake_case_is_error():
    result = CallToolResult(content=[TextContent(type="text", text="ok")], is_error=False)
    assert result.is_error is False
    assert not hasattr(result, "isError")


def test_real_call_tool_result_is_error_true_round_trips():
    result = CallToolResult(content=[TextContent(type="text", text="boom")], is_error=True)
    assert result.is_error is True
