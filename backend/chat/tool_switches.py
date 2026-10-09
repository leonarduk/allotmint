"""Admin on/off switches for the chat assistant's tools (``mcp.mcp_tools`` in config.yaml).

Every tool, MCP or local, is on unless the admin config sets it to false. The
chat agents drop switched-off tools from the list the model sees and refuse a
call to one, so the switch holds even when the MCP server runs elsewhere (its own
Lambda with its own config.yaml) and does not see the admin page's change.

A caller other than the chat page (the trend-watch agent, #10476) can narrow a
turn further with a :class:`ToolPolicy`: an allowlist of tool names, a cap on the
number of calls, and a record of every call made, for the evidence it reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, TypeVar

from backend import config_module

T = TypeVar("T")

# Read-only tools the trend-watch investigation may call (#10476). Nothing that
# writes: no price triggers, issues, data fixes or file exports. A test checks it.
TREND_WATCH_TOOLS: FrozenSet[str] = frozenset(
    {
        "get_instrument_technicals",
        "get_instrument_fundamentals",
        "get_instrument_valuation",
        "get_peer_comparison",
        "get_instrument_timeseries",
        "get_portfolio",
        "get_transactions",
        "search_web",
        "get_nav_discount",
    }
)


def tool_enabled(name: str) -> bool:
    switches = getattr(config_module.config, "mcp_tools", None) or {}
    return switches.get(name, True) is not False


def enabled_tools(tools: Iterable[T]) -> List[T]:
    """The tools (anything with a ``name``) that are not switched off."""
    return [tool for tool in tools if tool_enabled(getattr(tool, "name"))]


def switched_off_message(name: str) -> str:
    return f"{name} is switched off in the admin config."


# How much of each tool result a ToolPolicy keeps (a timeseries can be megabytes).
MAX_RECORDED_RESULT_CHARS = 4000


@dataclass
class ToolPolicy:
    """Which tools one turn may use, how many calls it gets, and what it called."""

    allowed: Optional[FrozenSet[str]] = None
    max_calls: Optional[int] = None
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def offers(self, name: str) -> bool:
        return self.allowed is None or name in self.allowed

    def refusal(self, name: str) -> Optional[str]:
        """Why a call to ``name`` is refused, or ``None`` when it may run."""

        if not tool_enabled(name):
            return switched_off_message(name)
        if not self.offers(name):
            return f"{name} is not available for this task."
        if self.max_calls is not None and len(self.calls) >= self.max_calls:
            return f"The limit of {self.max_calls} tool calls is reached; answer with what you have."
        return None

    def record(self, name: str, arguments: Mapping[str, Any], result: str, is_error: bool) -> None:
        # Kept for evidence, not replayed to the model, so a bounded prefix is enough.
        kept = result[:MAX_RECORDED_RESULT_CHARS]
        self.calls.append({"tool": name, "arguments": dict(arguments), "result": kept, "is_error": is_error})


def call_refusal(name: str, policy: Optional[ToolPolicy]) -> Optional[str]:
    """Why a call is refused: the admin switch alone, or the policy's fuller check."""

    if policy is not None:
        return policy.refusal(name)
    return None if tool_enabled(name) else switched_off_message(name)


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
