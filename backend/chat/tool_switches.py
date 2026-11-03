"""Admin on/off switches for the chat assistant's tools (``mcp.mcp_tools`` in config.yaml).

Every tool, MCP or local, is on unless the admin config sets it to false. MCP
tools also belong to a toolset (:data:`TOOLSETS`) switched by ``mcp.mcp_toolsets``:
a tool is on only if its toolset is on *and* its own switch is not false, so a
per-tool ``true`` never re-enables a tool whose toolset is off. Old switch keys of
tools merged in allotmint-pro#249 still apply (:data:`LEGACY_TOOL_NAMES`). The
chat agents drop switched-off tools from the list the model sees and refuse a
call to one, so the switch holds even when the MCP server runs elsewhere (its own
Lambda with its own config.yaml) and does not see the admin page's change.

A caller other than the chat page (the trend-watch agent, #10476) can narrow a
turn further with a :class:`ToolPolicy`: an allowlist of tool names, a cap on the
number of calls, and a record of every call made, for the evidence it reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple, TypeVar

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


# Mirrors allotmint-pro's ``allotmint_pro/mcp_server/tool_switches.py`` (pro#252),
# which owns these lists and enforces them on the MCP server itself. allotmint does
# not import the MCP server package, so keep this copy in step when pro's changes;
# a tool missing here is simply listed without a toolset (its toolset switch then
# only takes effect on the MCP server).
TOOLSETS: Dict[str, Tuple[str, ...]] = {
    "portfolio": (
        "list_owners",
        "get_portfolio",
        "get_account",
        "get_transactions",
        "summarise_transactions",
        "get_pension_forecast",
        "get_allocation",
        "get_investment_plan",
        "backtest_portfolio",
    ),
    "market": (
        "get_live_prices",
        "get_instrument",
        "get_data_freshness",
        "get_data_coverage",
        "get_data_quality_report",
        "get_instrument_fundamentals",
        "get_instrument_valuation",
        "get_instrument_technicals",
        "screen_instruments",
        "screen_portfolio_valuations",
        "screen_portfolio_technicals",
        "screen_risk_adjusted",
        "get_peer_comparison",
        "get_fund_facts",
        "get_fx_history",
        "get_market_rates",
        "get_credit_spreads",
        "get_credit_risk",
    ),
    "triggers": ("list_price_triggers", "create_price_trigger", "update_price_trigger", "delete_price_trigger"),
    "admin": ("list_data_files", "read_data_file", "create_github_issue", "add_instrument"),
    "web": ("search_web", "fetch_web_page"),
}

TOOLSET_OF: Dict[str, str] = {tool: toolset for toolset, names in TOOLSETS.items() for tool in names}

# Old switch key -> the tool it was merged into (allotmint-pro#249).
LEGACY_TOOL_NAMES: Dict[str, str] = {
    "get_group_portfolio": "get_portfolio",
    "list_owner_groups": "list_owners",
    "get_instrument_metadata": "get_instrument",
    "get_instrument_timeseries": "get_instrument",
}


def migrate_legacy_tool_switches(switches: Mapping[str, bool]) -> Dict[str, bool]:
    """``switches`` with old names of merged tools folded into the tools they became.

    Same rules as allotmint-pro's MCP server: an explicit key for the new tool
    wins over its old keys; otherwise the merged tool is off if *any* of its old
    keys is false, so a merge never switches back on a capability an admin
    switched off.
    """
    result = {name: value for name, value in switches.items() if name not in LEGACY_TOOL_NAMES}
    for old, value in switches.items():
        new = LEGACY_TOOL_NAMES.get(old)
        if new is None or new in switches:
            continue
        result[new] = result.get(new, True) and value is not False
    return result


def tool_switch_map() -> Dict[str, bool]:
    """The admin config's ``mcp_tools`` map with legacy names migrated; missing names are on."""
    switches = getattr(config_module.config, "mcp_tools", None) or {}
    return migrate_legacy_tool_switches(switches)


def toolset_switch_map() -> Dict[str, bool]:
    """The admin config's ``mcp_toolsets`` map (toolset name -> enabled); missing names are on."""
    return dict(getattr(config_module.config, "mcp_toolsets", None) or {})


def tool_enabled(name: str) -> bool:
    """True unless ``name``'s toolset or its own switch is off (an old name counts as its merged tool)."""
    canonical = LEGACY_TOOL_NAMES.get(name, name)
    toolset = TOOLSET_OF.get(canonical)
    if toolset is not None and toolset_switch_map().get(toolset, True) is False:
        return False
    return tool_switch_map().get(canonical, True) is not False


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
