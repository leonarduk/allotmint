"""The data steward's read-only view of the allotmint-pro MCP tools (#10471)."""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple

from backend.chat.bedrock_agent import _tool_result_to_bedrock_content
from backend.chat.tool_switches import data_steward_tool_allowed


def refusal_message(name: str) -> str:
    return f"{name} is not on the data steward's read-only tool allowlist."


class StewardTools(Protocol):
    async def list_tools(self) -> List[Dict[str, Any]]:
        """The callable tools as ``{name, description, input_schema}`` dicts."""

    async def call(self, name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
        """Run one tool; return ``(text, is_error)``."""


class McpStewardTools:
    """An MCP session filtered to ``DATA_STEWARD_READ_ONLY_TOOLS``.

    The filter is applied twice: tools off the allowlist are never offered to the
    model, and a call to one is refused here without reaching the server.
    """

    def __init__(self, session: Any) -> None:
        self._session = session

    async def list_tools(self) -> List[Dict[str, Any]]:
        result = await self._session.list_tools()
        return [
            {"name": tool.name, "description": tool.description or tool.name, "input_schema": tool.input_schema}
            for tool in result.tools
            if data_steward_tool_allowed(tool.name)
        ]

    async def call(self, name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
        if not data_steward_tool_allowed(name):
            return refusal_message(name), True
        result = await self._session.call_tool(name, arguments)
        return _tool_result_to_bedrock_content(result)[0]["text"], bool(result.is_error)
