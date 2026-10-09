"""Admin on/off switches for the chat assistant's tools (``mcp.mcp_tools`` in config.yaml).

Every tool, MCP or local, is on unless the admin config sets it to false. The
chat agents drop switched-off tools from the list the model sees and refuse a
call to one, so the switch holds even when the MCP server runs elsewhere (its own
Lambda with its own config.yaml) and does not see the admin page's change.

A caller may also pass an ``allowed`` set of tool names (e.g. a bot's read-only
allowlist); tools outside it are hidden and refused the same way.
"""

from __future__ import annotations

from typing import AbstractSet, Iterable, List, Optional, TypeVar

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


def tool_allowed(name: str, allowed: Optional[AbstractSet[str]]) -> bool:
    """Switched on and, when ``allowed`` is given, in it."""
    return tool_enabled(name) and (allowed is None or name in allowed)


def allowed_tools_only(tools: Iterable[T], allowed: Optional[AbstractSet[str]]) -> List[T]:
    """The tools (anything with a ``name``) in ``allowed``; all of them when ``allowed`` is None."""
    return [tool for tool in tools if allowed is None or getattr(tool, "name") in allowed]


def refused_message(name: str, allowed: Optional[AbstractSet[str]]) -> str:
    if not tool_enabled(name):
        return switched_off_message(name)
    return f"{name} is not in this conversation's allowed tools."
