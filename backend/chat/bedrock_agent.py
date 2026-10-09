"""Bedrock Converse API tool-calling loop against the allotmint-pro MCP server."""

from __future__ import annotations

import asyncio
import logging
import random
from functools import lru_cache
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import ConnectionError as BotocoreConnectionError
from mcp.types import CallToolResult, Tool

from backend.chat.local_tools import LocalTools, merge_tool_lists
from backend.chat.mcp_tools_client import mcp_session
from backend.chat.tool_switches import switched_off_message, tool_enabled
from backend.chat.turn_limits import TurnLimits, not_allowed_message
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Caps how many tool-call round trips one chat turn can make before giving up,
# so a model stuck re-calling tools can't run away with the Lambda's timeout.
MAX_TOOL_ITERATIONS = 5

# Retry policy for transient converse() failures (#7611): up to 3 retries with
# exponential backoff (1s, 2s, 4s) plus jitter. This is the only retry layer --
# botocore's own retries are disabled on the client below so attempts don't
# multiply (botocore legacy mode would otherwise retry each attempt 4 more times).
CONVERSE_MAX_RETRIES = 3
CONVERSE_RETRY_BASE_DELAY_SECONDS = 1.0
TRANSIENT_BEDROCK_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "ServiceUnavailable",
        "InternalServerException",
        "InternalServerError",
        "ModelNotReadyException",
        "ModelTimeoutException",
    }
)


@lru_cache(maxsize=1)
def _bedrock_client():
    """Process-wide bedrock-runtime client, built once (see instruments.py's
    ``_s3_client()`` for the same rationale: boto3 client construction
    re-resolves credentials/config every time, which is too slow to redo per
    chat turn)."""

    return boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 1}))


def _is_transient_converse_error(exc: Exception) -> bool:
    """True for throttling/5xx/connection failures worth retrying; False for
    validation, access-denied and other client errors that would fail again."""

    if isinstance(exc, BotocoreConnectionError):
        return True
    if not isinstance(exc, ClientError):
        return False
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
    return error.get("Code") in TRANSIENT_BEDROCK_ERROR_CODES or status >= 500


async def _converse_with_retry(bedrock: Any, **kwargs: Any) -> Dict[str, Any]:
    """Call ``bedrock.converse`` off the event loop, retrying transient failures.

    Every attempt resends the same ``kwargs`` (including the same ``messages``
    list object), so a retry never rebuilds or duplicates conversation state.
    """

    attempt = 0
    while True:
        try:
            # bedrock.converse() is a blocking boto3 call; run it off the
            # event loop thread so a slow Bedrock response doesn't stall
            # other concurrent requests being served by the same process.
            return await asyncio.to_thread(bedrock.converse, **kwargs)
        except Exception as exc:
            if attempt >= CONVERSE_MAX_RETRIES or not _is_transient_converse_error(exc):
                raise
            delay = CONVERSE_RETRY_BASE_DELAY_SECONDS * 2**attempt
            delay += random.uniform(0, delay / 2)  # nosec B311 - jitter, not crypto
            logger.warning(
                "Bedrock converse() attempt %d/%d failed transiently, retrying in %.1fs: %s",
                attempt + 1,
                CONVERSE_MAX_RETRIES + 1,
                delay,
                sanitise_log_value(exc),
            )
            await asyncio.sleep(delay)
            attempt += 1


def _tool_to_bedrock_spec(tool: Tool) -> Dict[str, Any]:
    return {
        "toolSpec": {
            "name": tool.name,
            "description": tool.description or tool.name,
            "inputSchema": {"json": tool.input_schema},
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
    local_tools: Optional[LocalTools] = None,
    system_prompt: Optional[str] = None,
    limits: Optional[TurnLimits] = None,
) -> str:
    """Run one user turn through the Bedrock tool-calling loop and return the reply.

    ``history`` is ``[{"role": "user"|"assistant", "content": "..."}, ...]`` —
    the caller resends the full prior conversation each turn; nothing is
    persisted server-side in this first pass. ``local_tools`` are offered
    alongside the MCP tools and run in-process (see ``backend.chat.local_tools``).
    ``limits`` optionally restricts the tools and records each call (see
    :mod:`backend.chat.turn_limits`).
    """

    messages: List[Dict[str, Any]] = [
        {"role": item["role"], "content": [{"text": item["content"]}]} for item in history
    ]
    messages.append({"role": "user", "content": [{"text": message}]})
    _validate_message_alternation(messages)

    bedrock = _bedrock_client()

    async with mcp_session(mcp_server_url) as session:
        tools_result = await session.list_tools()
        tools = merge_tool_lists(tools_result.tools, local_tools)
        if limits is not None:
            tools = [tool for tool in tools if limits.allows(tool.name)]
        tool_config = {"tools": [_tool_to_bedrock_spec(tool) for tool in tools]}
        max_iterations = (limits.max_iterations if limits else None) or MAX_TOOL_ITERATIONS
        extra: Dict[str, Any] = {"system": [{"text": system_prompt}]} if system_prompt else {}
        if limits is not None and limits.max_tokens:
            extra["inferenceConfig"] = {"maxTokens": limits.max_tokens}

        for _ in range(max_iterations):
            response = await _converse_with_retry(
                bedrock,
                modelId=bedrock_model_id,
                messages=messages,
                toolConfig=tool_config,
                **extra,
            )
            if limits is not None:
                usage = response.get("usage") or {}
                limits.add_usage(usage.get("inputTokens"), usage.get("outputTokens"))
            output_message = response["output"]["message"]
            messages.append(output_message)

            tool_uses = [block["toolUse"] for block in output_message["content"] if "toolUse" in block]
            if not tool_uses:
                text_blocks = [block["text"] for block in output_message["content"] if "text" in block]
                return "\n".join(text_blocks)

            tool_result_content = []
            for tool_use in tool_uses:
                refusal = None
                if not tool_enabled(tool_use["name"]):
                    refusal = switched_off_message(tool_use["name"])
                elif limits is not None and not limits.allows(tool_use["name"]):
                    refusal = not_allowed_message(tool_use["name"])
                if refusal is not None:
                    if limits is not None:
                        limits.record_call(tool_use["name"], tool_use.get("input") or {}, refusal, True)
                    tool_result_content.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_use["toolUseId"],
                                "content": [{"text": refusal}],
                                "status": "error",
                            }
                        }
                    )
                    continue
                if local_tools is not None and local_tools.handles(tool_use["name"]):
                    text, is_error = local_tools.call(tool_use["name"], tool_use.get("input") or {})
                    if limits is not None:
                        limits.record_call(tool_use["name"], tool_use.get("input") or {}, text, is_error)
                    tool_result_content.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_use["toolUseId"],
                                "content": [{"text": text}],
                                "status": "error" if is_error else "success",
                            }
                        }
                    )
                    continue
                try:
                    result = await session.call_tool(tool_use["name"], tool_use.get("input") or {})
                    content = _tool_result_to_bedrock_content(result)
                    status = "error" if result.is_error else "success"
                except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
                    logger.warning(
                        "MCP tool call %s failed: %s",
                        sanitise_log_value(tool_use["name"]),
                        sanitise_log_value(exc),
                    )
                    content = [{"text": f"Tool call failed: {exc}"}]
                    status = "error"
                if limits is not None:
                    text = "\n".join(block.get("text", "") for block in content)
                    limits.record_call(tool_use["name"], tool_use.get("input") or {}, text, status == "error")
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

    raise RuntimeError(f"Tool-calling loop did not converge after {max_iterations} iterations")
