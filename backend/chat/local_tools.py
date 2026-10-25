"""Chat tools handled by this backend rather than the MCP data server.

The MCP server only answers data questions. Moving the user around the app is
a UI action, so it lives here: the ``navigate_to_page`` tool records where the
model asked to go, and ``POST /chat`` returns it as ``navigate_to`` for the
client to follow.

The client sends the pages it can show (``ChatRequest.pages``), so the route
list stays owned by the frontend and only pages enabled for this user are
offered. The tool's ``path`` is an enum of exactly those paths, and a call with
any other value is rejected, so the model cannot send the user to an arbitrary
URL.

With ``data_tools=True`` (the chat route sets it) it also offers in-process
data tools, currently ``get_nav_discount`` (``backend.chat.nav_discount_tool``).
With ``file_exports=True`` it offers ``export_file``
(``backend.chat.export_file_tool``), which saves a table as a CSV, Excel or
Word file; the files are collected in ``files`` for ``POST /chat`` to return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from mcp.types import Tool

from backend.chat import export_file_tool, nav_discount_tool
from backend.chat.tool_switches import ToolPolicy, enabled_tools

NAVIGATE_TOOL_NAME = "navigate_to_page"


@dataclass(frozen=True)
class ChatPage:
    path: str
    label: str


@dataclass
class LocalTools:
    """Local tools for one chat turn, plus the navigation and files they produced."""

    pages: Sequence[ChatPage] = ()
    data_tools: bool = False
    file_exports: bool = False
    navigate_to: Optional[str] = field(default=None, init=False)
    files: List[export_file_tool.ExportedFile] = field(default_factory=list, init=False)

    def tools(self) -> List[Tool]:
        data_tools = [nav_discount_tool.TOOL] if self.data_tools else []
        export_tools = [export_file_tool.TOOL] if self.file_exports else []
        return self._navigate_tools() + data_tools + export_tools

    def _navigate_tools(self) -> List[Tool]:
        if not self.pages:
            return []
        listing = "; ".join(f"{page.path} ({page.label})" for page in self.pages)
        return [
            Tool(
                name=NAVIGATE_TOOL_NAME,
                description=(
                    "Open a page of the AllotMint app for the user. Use this when the "
                    "user asks to go to, open or show a page. Available pages: " + listing
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "enum": [page.path for page in self.pages],
                            "description": "Path of the page to open.",
                        }
                    },
                    "required": ["path"],
                },
            )
        ]

    def handles(self, name: str) -> bool:
        if name == nav_discount_tool.TOOL_NAME:
            return self.data_tools
        if name == export_file_tool.TOOL_NAME:
            return self.file_exports
        return bool(self.pages) and name == NAVIGATE_TOOL_NAME

    def call(self, name: str, arguments: Mapping[str, Any]) -> Tuple[str, bool]:
        """Run a local tool; return ``(text for the model, is_error)``."""

        if name == nav_discount_tool.TOOL_NAME and self.data_tools:
            return nav_discount_tool.call(arguments)
        if name == export_file_tool.TOOL_NAME and self.file_exports:
            return self._export_file(arguments)
        if name != NAVIGATE_TOOL_NAME:
            return f"Unknown local tool {name}", True
        path = arguments.get("path")
        page = next((page for page in self.pages if page.path == path), None)
        if page is None:
            allowed = ", ".join(page.path for page in self.pages)
            return f"Unknown page {path!r}; choose one of: {allowed}", True
        self.navigate_to = page.path
        return f"Opening {page.label} ({page.path}) for the user.", False

    def _export_file(self, arguments: Mapping[str, Any]) -> Tuple[str, bool]:
        if len(self.files) >= export_file_tool.MAX_FILES_PER_TURN:
            return f"export_file: at most {export_file_tool.MAX_FILES_PER_TURN} files per reply", True
        text, is_error, exported = export_file_tool.call(arguments)
        if exported is not None:
            total = sum(len(item.content) for item in self.files) + len(exported.content)
            if total > export_file_tool.MAX_TURN_BYTES:
                return "export_file: the files for this reply are too large in total", True
            self.files.append(exported)
        return text, is_error


# Short descriptions for the admin on/off switches (GET /config/mcp-tools); the
# model-facing descriptions are long. A local tool missing here is still
# listed, with its model-facing description.
_ADMIN_DESCRIPTIONS: Dict[str, str] = {
    NAVIGATE_TOOL_NAME: "Open a page of the app for the user.",
    nav_discount_tool.TOOL_NAME: "NAV premium/discount for a closed-end fund.",
    export_file_tool.TOOL_NAME: "Save a table as a CSV, Excel or Word download.",
}


def local_tool_summaries() -> List[Dict[str, str]]:
    """Every tool ``LocalTools`` can offer, as ``{name, description}`` for the admin switches (#8504).

    Built from ``LocalTools.tools()`` with every option on, so a new local tool
    is listed (and can be switched off) without editing the config route.
    """

    every = LocalTools(pages=(ChatPage(path="/", label="Home"),), data_tools=True, file_exports=True).tools()
    return [
        {"name": tool.name, "description": _ADMIN_DESCRIPTIONS.get(tool.name, tool.description or "")} for tool in every
    ]


def merge_tool_lists(
    mcp_tools: Sequence[Tool], local: Optional[LocalTools], policy: Optional[ToolPolicy] = None
) -> List[Tool]:
    """MCP tools plus local ones; a local tool replaces an MCP tool of the same name.

    Tools switched off in the admin config are left out (see ``tool_switches``),
    as are tools outside ``policy``'s allowlist when one is given.
    """

    local_tools = local.tools() if local else []
    local_names = {tool.name for tool in local_tools}
    merged = enabled_tools([tool for tool in mcp_tools if tool.name not in local_names] + local_tools)
    return [tool for tool in merged if policy is None or policy.offers(tool.name)]


# Sent on every chat turn. Without it a model that is not offered a tool for
# something (an older MCP server, or the tool switched off in the admin config)
# tends to say AllotMint has no such data -- e.g. "no P/E, P/B or yield" when
# the fundamentals tools exist (#8685). Kept tool-agnostic: the tool list and
# its descriptions are what say which data is available on this turn.
CORE_SYSTEM_PROMPT = (
    "You are the AllotMint assistant. Answer questions about the user's portfolios, "
    "transactions and instruments with the tools you are given, and read each tool's "
    "description to see what data it returns; market tools can include valuation "
    "fundamentals such as P/E, P/B and dividend yield. When a tool result names its "
    "source or an as-of date, cite them with the figures. If none of your tools covers "
    "a request, say that you have no tool for it here; do not claim AllotMint has no "
    "such data, and do not make figures up."
)

# The portfolio review playbook (#9125). Steps name capabilities, not tool names,
# for the same reason as above: whichever tools this turn offers are the ones to
# use, and a step with no tool is reported as missing rather than guessed. It is
# decision support -- findings and options -- never a personal recommendation.
PORTFOLIO_REVIEW_GUIDANCE = (
    "When the user asks you to review a portfolio, or to help think through a decision "
    "about a holding (buying more, trimming, selling, rebalancing), work through these "
    "steps with whichever tools you have, and say which steps you could not do:\n"
    "1. Holdings: get the priced holdings for the owner (ask which owner if it is not "
    "clear). Note the total value, the largest positions and their share of the total, "
    "the account types (ISA, SIPP, GIA and so on) and how many trades remain this month.\n"
    "2. Screens: run the portfolio-wide valuation and technicals screens and look at the "
    "outliers, for example cheap but in a downtrend, expensive and overbought, or well "
    "behind its benchmark.\n"
    "3. News: for the largest positions and anything the screens flagged, look for recent "
    "news if you have a search tool.\n"
    "4. Constraints: take account of the tax wrapper and trading limits. If you have no "
    "data for a constraint such as remaining tax allowances, say so; do not assume.\n"
    "5. Reply with a short review under these headings: Snapshot; What stands out; "
    "Options to consider (each with its trade-offs, including leaving things as they "
    "are); What to watch; Data caveats (stale prices, missing data, failed lookups).\n"
    "Present findings and options, not personal recommendations: do not tell the user to "
    "buy or sell anything, because the decision is theirs. If they ask what they should "
    "do, lay out the options and what each depends on, and say that you are not a "
    "regulated financial adviser."
)

# The owner's stored plan (#10613). Two fresh chats asking the same drift question
# disagreed on whether a plan existed: one used it, the other said none was
# recorded. The tool is named because the rule is about that one record, and an
# earlier answer in the history is never a substitute: the plan can change.
INVESTMENT_PLAN_GUIDANCE = (
    "Before you compare an owner's allocation with any target or model mix (60/40, "
    "Golden Butterfly, All Weather, Permanent Portfolio and so on), or answer a question "
    "about drift, rebalancing, targets, a portfolio review or whether they are on track, "
    "call get_investment_plan for that owner in this turn, even if an earlier reply "
    "mentioned their plan. Then:\n"
    "- If it returns a plan, say so and report the plan's own target and drift. If the "
    "user named a different model mix, show the plan target and the named mix as separate, "
    "labelled comparisons.\n"
    "- Say the owner has no investment plan only when get_investment_plan returned "
    "plan_recorded false in this turn.\n"
    "- If the call failed, was refused, or you have no get_investment_plan tool, say that "
    "you could not read the owner's plan, and give the reason if you have one; do not say "
    "that no plan is recorded.\n"
    "When you compare with a named model mix, state its weights once and use exactly those "
    "weights in any table."
)

BASE_SYSTEM_PROMPT = f"{CORE_SYSTEM_PROMPT}\n\n{INVESTMENT_PLAN_GUIDANCE}\n\n{PORTFOLIO_REVIEW_GUIDANCE}"


def build_system_prompt(context: Mapping[str, Any] | None, signed_in_owner: Optional[str] = None) -> str:
    """The system prompt for one chat turn: the base guidance, then who is asking and the page context."""

    lines = [line for line in (system_prompt_for_user(signed_in_owner), system_prompt_from_context(context)) if line]
    return "\n\n".join([BASE_SYSTEM_PROMPT, *lines])


def system_prompt_for_user(owner: Optional[str]) -> Optional[str]:
    """Tell the model whose portfolio "my" means, so "my SIPP" needs no clarifying question (#10813).

    ``owner`` is resolved server-side from the signed-in identity, never taken
    from the request body. It is context only: tool calls stay subject to the
    MCP server's own access checks.
    """

    if not owner:
        return None
    return (
        f'The signed-in user is the owner {owner}. When they say "my", "mine" or "I" '
        f'(for example "my SIPP" or "my portfolio"), they mean the owner {owner}; '
        "do not ask which owner they mean."
    )


def system_prompt_from_context(context: Mapping[str, Any] | None) -> Optional[str]:
    """Tell the model which page, and whose portfolio, the user is looking at, so "this stock" resolves."""

    if not context:
        return None
    ticker = context.get("ticker")
    line = f"The user is currently viewing the page {context['path']}."
    if ticker:
        line += f' It is about the instrument {ticker}; treat "this stock" or "this" as {ticker}.'
    owner = context.get("owner")
    group = context.get("group")
    if owner:
        line += f' The app has the owner {owner} selected; treat "this portfolio" as {owner}\'s.'
    elif group:
        line += f' The app has the group {group} selected; treat "this portfolio" as that group\'s.'
    return line


def pages_from_request(pages: Sequence[Mapping[str, Any]] | None) -> List[ChatPage]:
    return [ChatPage(path=str(item["path"]), label=str(item["label"])) for item in pages or ()]
