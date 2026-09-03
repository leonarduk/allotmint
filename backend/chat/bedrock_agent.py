"""Bedrock Converse API tool-calling loop against the allotmint-pro MCP server."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Dict, List

import boto3
from mcp.types import CallToolResult, Tool

from backend.chat.mcp_tools_client import mcp_session
from backend.logging_setup import sanitise_log_value

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
    """Convert an MCP ``CallToolResult`` into Bedrock ``toolResult`` content blocks.

    allotmint-pro's MCP tools only ever return text content today, but a
    non-text block (e.g. ``ImageContent``/``EmbeddedResource``) is rendered
    as its JSON representation rather than silently dropped -- the model
    still sees *something* instead of a misleading "(no output)" for a tool
    call that actually succeeded.
    """

    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "model_dump_json"):
            parts.append(block.model_dump_json())
        else:
            parts.append(str(block))
    return [{"text": "\n".join(parts) or "(no output)"}]


def _validate_message_alternation(messages: List[Dict[str, Any]]) -> None:
    """Raise ``ValueError`` if consecutive messages share a role.

    Bedrock's Converse API requires strict user/assistant alternation and
    rejects a violation with an HTTP 400 from deep inside boto3 -- this
    check surfaces the same problem as a clean, catchable error at the
    point the conversation is assembled instead.
    """

    for previous, current in zip(messages, messages[1:]):
        if previous["role"] == current["role"]:
            raise ValueError(
                "Chat history must alternate user/assistant roles; got consecutive " f"'{current['role']}' messages"
            )


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
    _validate_message_alternation(messages)

    bedrock = _bedrock_client()

    async with mcp_session(mcp_server_url) as session:
        tools_result = await session.list_tools()
        tool_config = {"tools": [_tool_to_bedrock_spec(tool) for tool in tools_result.tools]}

        for _ in range(MAX_TOOL_ITERATIONS):
            # bedrock.converse() is a blocking boto3 call; run it off the
            # event loop thread so a slow Bedrock response doesn't stall
            # other concurrent requests being served by the same process.
            response = await asyncio.to_thread(
                bedrock.converse,
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
                    logger.warning(
                        "MCP tool call %s failed: %s",
                        sanitise_log_value(tool_use["name"]),
                        sanitise_log_value(exc),
                    )
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
