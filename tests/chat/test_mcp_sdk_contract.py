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

import inspect
import typing

from mcp.client.streamable_http import TransportStreams, streamable_http_client
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


def test_real_streamable_http_client_accepts_http_client_kwarg_not_auth():
    # mcp_tools_client.py wires auth via a pre-configured httpx2.AsyncClient
    # passed as `http_client=`, not the old `auth=` kwarg mcp 1.x accepted.
    # mcp_tools_client.py's own tests mock this function, so they can't catch
    # a real signature drift -- this checks the actual installed export.
    params = inspect.signature(streamable_http_client).parameters
    assert "http_client" in params
    assert "auth" not in params


def test_real_streamable_http_client_yields_a_two_tuple():
    # mcp_tools_client.py does `async with streamable_http_client(...) as
    # (read_stream, write_stream):`. mcp 1.x's streamablehttp_client yielded
    # a 3-tuple; unpacking a real 3-tuple into two names would raise
    # ValueError at runtime, which only a real-signature check can catch.
    assert len(typing.get_args(TransportStreams)) == 2
