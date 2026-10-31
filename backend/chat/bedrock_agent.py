"""Bedrock Converse API tool-calling loop against the allotmint-pro MCP server."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import ConnectionError as BotocoreConnectionError
from mcp.types import CallToolResult, Tool

from backend.chat.local_tools import LocalTools, merge_tool_lists
from backend.chat.mcp_tools_client import log_tool_call, mcp_session
from backend.chat.plan_guard import PlanGuard
from backend.chat.tool_switches import ToolPolicy, call_refusal
from backend.chat.turn_limits import TurnLimits, not_allowed_message
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Caps how many tool-call round trips one chat turn can make before giving up,
# so a model stuck re-calling tools can't run away with the Lambda's timeout.
MAX_TOOL_ITERATIONS = 5

# Bounds on the tool output put into the reply when a turn hits the cap (#7623),
# so one oversized result can't flood the chat window.
CAP_REPLY_MAX_RESULTS = 5
CAP_REPLY_MAX_CHARS_PER_RESULT = 1000

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


async def _call_tool(
    session: Any, local_tools: Optional[LocalTools], name: str, arguments: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], str]:
    """Run one tool call, local or MCP; return ``(toolResult content, status)``.

    Local and MCP calls share one error boundary, as in the OpenAI path
    (``openai_compat_agent``): an exception from either is surfaced to the
    model as a failed tool call instead of aborting the turn (#8201).
    """

    try:
        if local_tools is not None and local_tools.handles(name):
            text, is_error = local_tools.call(name, arguments)
            return [{"text": text}], "error" if is_error else "success"
        result = await session.call_tool(name, arguments)
        return _tool_result_to_bedrock_content(result), "error" if result.is_error else "success"
    except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
        logger.warning(
            "Tool call %s failed: %s",
            sanitise_log_value(name),
            sanitise_log_value(exc),
        )
        return [{"text": f"Tool call failed: {exc}"}], "error"


def iteration_cap_reply(
    max_iterations: int, results: List[Tuple[str, str]], limits: Optional[TurnLimits] = None
) -> str:
    """Reply for a turn that used up its tool-call cap without a final answer.

    ``results`` is ``[(tool name, result text), ...]`` from the last round of
    tool calls. They are shown, bounded, instead of raising, so the work
    already done reaches the user rather than a bare 500 (#7623). Still
    raises ``RuntimeError`` when ``limits.raise_at_cap`` is set. Shared by
    both provider loops (``openai_compat_agent`` too).
    """

    if limits is not None and limits.raise_at_cap:
        raise RuntimeError(f"Tool-calling loop did not converge after {max_iterations} iterations")
    lines = [
        f"I reached the tool-call limit for this turn ({max_iterations} steps) before finishing my answer. "
        "Here are the latest tool results; try asking again or narrowing the question."
    ]
    for name, text in results[:CAP_REPLY_MAX_RESULTS]:
        if len(text) > CAP_REPLY_MAX_CHARS_PER_RESULT:
            text = text[:CAP_REPLY_MAX_CHARS_PER_RESULT] + " ... (truncated)"
        lines.append(f"{name}:\n{text}")
    if len(results) > CAP_REPLY_MAX_RESULTS:
        lines.append(f"(and {len(results) - CAP_REPLY_MAX_RESULTS} more tool results not shown)")
    return "\n\n".join(lines)


def _validate_message_alternation(messages: List[Dict[str, Any]]) -> None:
    """Raise ``ValueError`` unless the messages start with ``user`` and alternate roles.

    Bedrock's Converse API requires the conversation to open with a user
    turn and to alternate user/assistant strictly, and rejects a violation
    with an HTTP 400 from deep inside boto3 -- this check surfaces the same
    problem as a clean, catchable error at the point the conversation is
    assembled instead (#7617).
    """

    if messages and messages[0]["role"] != "user":
        raise ValueError(f"Chat history must start with a 'user' message; got '{messages[0]['role']}'")
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
    tool_policy: Optional[ToolPolicy] = None,
    limits: Optional[TurnLimits] = None,
) -> str:
    """Run one user turn through the Bedrock tool-calling loop and return the reply.

    ``history`` is ``[{"role": "user"|"assistant", "content": "..."}, ...]`` —
    the caller resends the full prior conversation each turn; nothing is
    persisted server-side in this first pass. ``local_tools`` are offered
    alongside the MCP tools and run in-process (see ``backend.chat.local_tools``).
    ``tool_policy`` narrows the tools offered, caps the calls and records them
    (see ``backend.chat.tool_switches.ToolPolicy``).
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
        tools = merge_tool_lists(tools_result.tools, local_tools, tool_policy)
        if limits is not None:
            tools = [tool for tool in tools if limits.allows(tool.name)]
        tool_config = {"tools": [_tool_to_bedrock_spec(tool) for tool in tools]}
        max_iterations = (limits.max_iterations if limits else None) or MAX_TOOL_ITERATIONS
        extra: Dict[str, Any] = {"system": [{"text": system_prompt}]} if system_prompt else {}
        if limits is not None and limits.max_tokens:
            extra["inferenceConfig"] = {"maxTokens": limits.max_tokens}
        plan_guard = PlanGuard(message, (tool.name for tool in tools))
        # Set before the loop so the cap reply below can always read it.
        last_results: List[Tuple[str, str]] = []

        for iteration in range(max_iterations):
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
                reminder = plan_guard.reminder(max_iterations - iteration - 1)
                if reminder is None:
                    text_blocks = [block["text"] for block in output_message["content"] if "text" in block]
                    return "\n".join(text_blocks)
                messages.append({"role": "user", "content": [{"text": reminder}]})
                continue

            tool_result_content = []
            last_results = []
            for tool_use in tool_uses:
                plan_guard.saw_call(tool_use["name"])
                started = time.perf_counter()
                refusal = call_refusal(tool_use["name"], tool_policy)
                if refusal is None and limits is not None and not limits.allows(tool_use["name"]):
                    refusal = not_allowed_message(tool_use["name"])
                if refusal is not None:
                    # Logged in the turn limits; not recorded in the policy, so it does not use up its cap.
                    if limits is not None:
                        limits.record_call(tool_use["name"], tool_use.get("input") or {}, refusal, True)
                    log_tool_call(tool_use["name"], "refused", started)
                    last_results.append((tool_use["name"], refusal))
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
                content, status = await _call_tool(session, local_tools, tool_use["name"], tool_use.get("input") or {})
                log_tool_call(tool_use["name"], "ok" if status == "success" else "error", started)
                if tool_policy is not None:
                    tool_policy.record(
                        tool_use["name"], tool_use.get("input") or {}, content[0]["text"], status == "error"
                    )
                text = "\n".join(block.get("text", "") for block in content)
                last_results.append((tool_use["name"], text))
                if limits is not None:
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

    # Only reachable after a tool round: a text-only reply on the last
    # iteration returns above (the plan guard never reminds at the cap).
    return iteration_cap_reply(max_iterations, last_results, limits)
