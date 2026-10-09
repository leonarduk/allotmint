"""OpenAI-compatible chat-completions tool-calling loop against the allotmint-pro MCP server.

Covers any provider exposing ``POST {base_url}/chat/completions`` with
OpenAI-style ``tools``/``tool_calls`` -- in practice a local Ollama
(``http://localhost:11434/v1``) or the DeepSeek API -- so local development
doesn't need AWS Bedrock. Mirrors ``bedrock_agent.run_chat_turn``'s loop
shape; called over plain ``httpx`` rather than the ``openai`` SDK so the
Lambda image needs no new dependency.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from mcp.types import Tool

from backend.chat.bedrock_agent import (
    MAX_TOOL_ITERATIONS,
    _tool_result_to_bedrock_content,
    _validate_message_alternation,
)
from backend.chat.local_tools import LocalTools, merge_tool_lists
from backend.chat.mcp_tools_client import mcp_session
from backend.chat.tool_switches import switched_off_message, tool_enabled
from backend.chat.turn_limits import TurnLimits, not_allowed_message
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Local models on consumer hardware can take tens of seconds per completion,
# especially on the first call while Ollama loads the model into memory.
REQUEST_TIMEOUT_SECONDS = 180.0


def _tool_to_openai_spec(tool: Tool) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or tool.name,
            "parameters": tool.input_schema,
        },
    }


def _parse_tool_arguments(raw: Any) -> Dict[str, Any]:
    """Return a tool call's arguments as a dict.

    The OpenAI schema sends ``arguments`` as a JSON string, but some
    compatible servers send an already-decoded object; an empty or ``null``
    value means "no arguments".
    """

    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    return json.loads(raw)


async def _complete(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    limits: Optional[TurnLimits] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "messages": messages, "tools": tools}
    if limits is not None and limits.max_tokens:
        payload["max_tokens"] = limits.max_tokens
    response = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload)
    response.raise_for_status()
    body = response.json()
    if limits is not None:
        usage = body.get("usage") or {}
        limits.add_usage(usage.get("prompt_tokens"), usage.get("completion_tokens"))
    return body["choices"][0]["message"]


async def run_chat_turn(
    message: str,
    history: List[Dict[str, str]],
    *,
    mcp_server_url: str,
    base_url: str,
    model: str,
    api_key: Optional[str] = None,
    local_tools: Optional[LocalTools] = None,
    system_prompt: Optional[str] = None,
    limits: Optional[TurnLimits] = None,
) -> str:
    """Run one user turn through an OpenAI-compatible tool-calling loop and return the reply.

    ``history`` has the same shape as ``bedrock_agent.run_chat_turn``'s.
    ``limits`` optionally restricts the tools and records each call (see
    :mod:`backend.chat.turn_limits`).
    """

    messages: List[Dict[str, Any]] = [{"role": item["role"], "content": item["content"]} for item in history]
    messages.append({"role": "user", "content": message})
    _validate_message_alternation(messages)
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async with (
        mcp_session(mcp_server_url) as session,
        httpx.AsyncClient(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS) as client,
    ):
        tools_result = await session.list_tools()
        offered = merge_tool_lists(tools_result.tools, local_tools)
        if limits is not None:
            offered = [tool for tool in offered if limits.allows(tool.name)]
        tools = [_tool_to_openai_spec(tool) for tool in offered]
        max_iterations = (limits.max_iterations if limits else None) or MAX_TOOL_ITERATIONS

        for _ in range(max_iterations):
            output_message = await _complete(
                client, base_url=base_url, model=model, messages=messages, tools=tools, limits=limits
            )
            tool_calls = output_message.get("tool_calls") or []
            messages.append(
                {"role": "assistant", "content": output_message.get("content") or "", "tool_calls": tool_calls}
                if tool_calls
                else {"role": "assistant", "content": output_message.get("content") or ""}
            )
            if not tool_calls:
                return output_message.get("content") or ""

            for tool_call in tool_calls:
                name = tool_call["function"]["name"]
                arguments: Any = tool_call["function"].get("arguments")
                failed = True
                try:
                    if not tool_enabled(name):
                        raise ValueError(switched_off_message(name))
                    if limits is not None and not limits.allows(name):
                        raise ValueError(not_allowed_message(name))
                    arguments = _parse_tool_arguments(arguments)
                    if local_tools is not None and local_tools.handles(name):
                        content, is_error = local_tools.call(name, arguments)
                        # OpenAI tool messages have no status field, so flag a
                        # rejected call the same way as a failed MCP call below.
                        if is_error:
                            content = f"Tool call failed: {content}"
                        failed = is_error
                    else:
                        result = await session.call_tool(name, arguments)
                        content = _tool_result_to_bedrock_content(result)[0]["text"]
                        failed = bool(getattr(result, "is_error", False))
                except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
                    logger.warning(
                        "MCP tool call %s failed: %s",
                        sanitise_log_value(name),
                        sanitise_log_value(exc),
                    )
                    content = f"Tool call failed: {exc}"
                if limits is not None:
                    limits.record_call(name, arguments, content, failed)
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": content})

    raise RuntimeError(f"Tool-calling loop did not converge after {max_iterations} iterations")
