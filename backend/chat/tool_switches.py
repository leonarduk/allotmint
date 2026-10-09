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


#: Name prefixes of tools that change data (allotmint-pro MCP: add_instrument,
#: create_issue, create/update/delete_price_trigger, ...). A background agent
#: that must stay read-only checks its allowlist against these (#10475).
WRITE_TOOL_PREFIXES = (
    "add_",
    "apply_",
    "backfill_",
    "create_",
    "delete_",
    "put_",
    "record_",
    "refresh_",
    "remove_",
    "restart_",
    "save_",
    "set_",
    "update_",
    "write_",
)
#: Read-only tools are named for what they return.
READ_TOOL_PREFIXES = ("get_", "list_", "summarise_", "search_", "screen_")


def is_read_only_tool_name(name: str) -> bool:
    """True for a tool named as a read (``get_...``) and not as a write."""
    return name.startswith(READ_TOOL_PREFIXES) and not name.startswith(WRITE_TOOL_PREFIXES)
