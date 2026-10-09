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


# Tools the data steward agent (backend/data_steward) may call (#10471). Phase 1
# is find/investigate/report only, so this is an allowlist of read-only tools:
# anything not named here -- price-trigger CRUD, create_github_issue,
# add_instrument, web fetch/search, and every future tool -- is never offered to
# the steward's model and is refused if it asks for it anyway.
DATA_STEWARD_READ_ONLY_TOOLS = frozenset(
    {
        "get_data_quality_report",
        "get_data_coverage",
        "get_data_freshness",
        "get_instrument",
        "get_live_prices",
        "get_fx_history",
        "list_data_files",
        "read_data_file",
        "list_owners",
        "get_portfolio",
    }
)


def data_steward_tool_allowed(name: str) -> bool:
    """True when the data steward may call ``name``: allowlisted and not switched off."""
    return name in DATA_STEWARD_READ_ONLY_TOOLS and tool_enabled(name)


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
    """True for a tool named as a read (``get_...``) and not as a write.

    A naming backstop only: the authoritative control is an explicit
    allowlist (e.g. ``backend.plan_brief.agent.READ_ONLY_TOOLS``), which this
    check guards against an obviously wrong entry.
    """
    return name.startswith(READ_TOOL_PREFIXES) and not name.startswith(WRITE_TOOL_PREFIXES)
