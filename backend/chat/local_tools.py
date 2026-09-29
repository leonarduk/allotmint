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
    """MCP tools plus local ones; a local tool replaces an MCP tool of the same name."""

    local_tools = local.tools() if local else []
    local_names = {tool.name for tool in local_tools}
    return [tool for tool in mcp_tools if tool.name not in local_names] + local_tools


def pages_from_request(pages: Sequence[Mapping[str, Any]] | None) -> List[ChatPage]:
    return [ChatPage(path=str(item["path"]), label=str(item["label"])) for item in pages or ()]
