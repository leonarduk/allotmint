"""Bedrock Converse API tool-calling loop against the allotmint-pro MCP server."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List

import boto3
from mcp.types import CallToolResult, Tool

from backend.chat.mcp_tools_client import mcp_session

logger = logging.getLogger(__name__)

# Caps how many tool-call round trips one chat turn can make before giving up,
# so a model stuck re-calling tools can't run away with the Lambda's timeout.
MAX_TOOL_ITERATIONS = 5


@lru_cache(maxsize=1)
def _bedrock_client():
    """Process-wide bedrock-runtime client, built once (see instruments.py's
    ``_s3_client()`` for the same rationale: boto3 client construction
    re-resolves credentials/config every time, which is too slow to redo per
    chat turn)."""

    return boto3.client("bedrock-runtime")


def _tool_to_bedrock_spec(tool: Tool) -> Dict[str, Any]:
    return {
        "toolSpec": {
            "name": tool.name,
            "description": tool.description or tool.name,
            "inputSchema": {"json": tool.inputSchema},
        }
    }


def _tool_result_to_bedrock_content(result: CallToolResult) -> List[Dict[str, Any]]:
    """Convert an MCP ``CallToolResult`` into Bedrock ``toolResult`` content blocks."""

    text_parts = [block.text for block in result.content if hasattr(block, "text")]
    return [{"text": "\n".join(text_parts) or "(no output)"}]


async def run_chat_turn(
    message: str,
    history: List[Dict[str, str]],
    *,
    mcp_server_url: str,
    bedrock_model_id: str,
) -> str:
    """Run one user turn through the Bedrock tool-calling loop and return the reply.

    ``history`` is ``[{"role": "user"|"assistant", "content": "..."}, ...]`` —
    the caller resends the full prior conversation each turn; nothing is
    persisted server-side in this first pass.
    """

    messages: List[Dict[str, Any]] = [
        {"role": item["role"], "content": [{"text": item["content"]}]} for item in history
    ]
    messages.append({"role": "user", "content": [{"text": message}]})

    bedrock = _bedrock_client()

    async with mcp_session(mcp_server_url) as session:
        tools_result = await session.list_tools()
        tool_config = {"tools": [_tool_to_bedrock_spec(tool) for tool in tools_result.tools]}

        for _ in range(MAX_TOOL_ITERATIONS):
            response = bedrock.converse(
                modelId=bedrock_model_id,
                messages=messages,
                toolConfig=tool_config,
            )
            output_message = response["output"]["message"]
            messages.append(output_message)

            tool_uses = [block["toolUse"] for block in output_message["content"] if "toolUse" in block]
            if not tool_uses:
                text_blocks = [block["text"] for block in output_message["content"] if "text" in block]
                return "\n".join(text_blocks)

            tool_result_content = []
            for tool_use in tool_uses:
                try:
                    result = await session.call_tool(tool_use["name"], tool_use.get("input") or {})
                    content = _tool_result_to_bedrock_content(result)
                    status = "error" if result.isError else "success"
                except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
                    logger.warning("MCP tool call %s failed: %s", tool_use["name"], exc)
                    content = [{"text": f"Tool call failed: {exc}"}]
                    status = "error"
                tool_result_content.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use["toolUseId"],
                            "content": content,
                            "status": status,
                        }
                    }
                )
            messages.append({"role": "user", "content": tool_result_content})

    raise RuntimeError(f"Tool-calling loop did not converge after {MAX_TOOL_ITERATIONS} iterations")
