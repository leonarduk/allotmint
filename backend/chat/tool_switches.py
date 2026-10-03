"""Admin on/off switches for the chat assistant's tools (``mcp.mcp_tools`` in config.yaml).

Every tool, MCP or local, is on unless the admin config sets it to false. The
chat agents drop switched-off tools from the list the model sees and refuse a
call to one, so the switch holds even when the MCP server runs elsewhere (its own
Lambda with its own config.yaml) and does not see the admin page's change.
"""

from __future__ import annotations

from typing import Iterable, List, TypeVar

from backend import config_module

T = TypeVar("T")


def tool_enabled(name: str) -> bool:
    switches = getattr(config_module.config, "mcp_tools", None) or {}
    return switches.get(name, True) is not False


def enabled_tools(tools: Iterable[T]) -> List[T]:
    """The tools (anything with a ``name``) that are not switched off."""
    return [tool for tool in tools if tool_enabled(getattr(tool, "name"))]


def switched_off_message(name: str) -> str:
    return f"{name} is switched off in the admin config."
