"""``get_nav_discount``: a chat tool answered in-process from ``backend.common.nav``.

The NAV store (``<data_root>/nav/navs.csv``) and the cached prices live with
this backend, so the tool runs here rather than on the MCP data server. It is
offered through :class:`backend.chat.local_tools.LocalTools`, and the admin
config can switch it off like any other tool (``mcp.mcp_tools``).
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Tuple

from mcp.types import Tool

from backend.common import nav

TOOL_NAME = "get_nav_discount"

TOOL = Tool(
    name=TOOL_NAME,
    description=(
        "Premium or discount to net asset value (NAV) for a listed closed-end fund such as a UK "
        "investment trust. Returns the latest recorded NAV per share, its date and source, the "
        "closing price on or just before that date (both in GBP), and premium_discount_pct "
        "(price/NAV - 1, as a percentage; negative means a discount). For other instruments, or "
        "when no NAV is recorded, the values are null and 'reason' says why. Do not estimate a NAV."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Full ticker including the exchange suffix, e.g. 3IN.L or HICL.L.",
            }
        },
        "required": ["ticker"],
    },
)


def call(arguments: Mapping[str, Any]) -> Tuple[str, bool]:
    """Run the tool; return ``(JSON text for the model, is_error)``."""

    ticker = str(arguments.get("ticker") or "").strip()
    if not ticker or ticker.startswith("."):
        return "get_nav_discount needs a ticker such as 3IN.L.", True
    try:
        result = nav.nav_discount(ticker)
    except (OSError, ValueError) as exc:
        # Surfaced to the model as a failed call (a bad CSV or metadata file), not swallowed.
        return f"get_nav_discount failed for {ticker}: {exc}", True
    return json.dumps(result.as_dict()), False
