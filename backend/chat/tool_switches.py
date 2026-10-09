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
