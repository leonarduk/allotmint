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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from mcp.types import Tool

from backend.chat.tool_switches import enabled_tools

NAVIGATE_TOOL_NAME = "navigate_to_page"


@dataclass(frozen=True)
class ChatPage:
    path: str
    label: str


@dataclass
class LocalTools:
    """Local tools for one chat turn, plus the navigation they requested."""

    pages: Sequence[ChatPage] = ()
    navigate_to: Optional[str] = field(default=None, init=False)

    def tools(self) -> List[Tool]:
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
        return bool(self.pages) and name == NAVIGATE_TOOL_NAME

    def call(self, name: str, arguments: Mapping[str, Any]) -> Tuple[str, bool]:
        """Run a local tool; return ``(text for the model, is_error)``."""

        if name != NAVIGATE_TOOL_NAME:
            return f"Unknown local tool {name}", True
        path = arguments.get("path")
        page = next((page for page in self.pages if page.path == path), None)
        if page is None:
            allowed = ", ".join(page.path for page in self.pages)
            return f"Unknown page {path!r}; choose one of: {allowed}", True
        self.navigate_to = page.path
        return f"Opening {page.label} ({page.path}) for the user.", False


def merge_tool_lists(mcp_tools: Sequence[Tool], local: Optional[LocalTools]) -> List[Tool]:
    """MCP tools plus local ones; a local tool replaces an MCP tool of the same name.

    Tools switched off in the admin config are left out (see ``tool_switches``).
    """

    local_tools = local.tools() if local else []
    local_names = {tool.name for tool in local_tools}
    return enabled_tools([tool for tool in mcp_tools if tool.name not in local_names] + local_tools)


# Sent on every chat turn. Without it a model that is not offered a tool for
# something (an older MCP server, or the tool switched off in the admin config)
# tends to say AllotMint has no such data -- e.g. "no P/E, P/B or yield" when
# the fundamentals tools exist (#8685). Kept tool-agnostic: the tool list and
# its descriptions are what say which data is available on this turn.
BASE_SYSTEM_PROMPT = (
    "You are the AllotMint assistant. Answer questions about the user's portfolios, "
    "transactions and instruments with the tools you are given, and read each tool's "
    "description to see what data it returns; market tools can include valuation "
    "fundamentals such as P/E, P/B and dividend yield. When a tool result names its "
    "source or an as-of date, cite them with the figures. If none of your tools covers "
    "a request, say that you have no tool for it here; do not claim AllotMint has no "
    "such data, and do not make figures up."
)


def build_system_prompt(context: Mapping[str, Any] | None) -> str:
    """The system prompt for one chat turn: the base guidance, then the page context if any."""

    context_line = system_prompt_from_context(context)
    return f"{BASE_SYSTEM_PROMPT}\n\n{context_line}" if context_line else BASE_SYSTEM_PROMPT


def system_prompt_from_context(context: Mapping[str, Any] | None) -> Optional[str]:
    """Tell the model which page the user is looking at, so "this stock" resolves."""

    if not context:
        return None
    ticker = context.get("ticker")
    line = f"The user is currently viewing the page {context['path']}."
    if ticker:
        line += f' It is about the instrument {ticker}; treat "this stock" or "this" as {ticker}.'
    return line


def pages_from_request(pages: Sequence[Mapping[str, Any]] | None) -> List[ChatPage]:
    return [ChatPage(path=str(item["path"]), label=str(item["label"])) for item in pages or ()]
