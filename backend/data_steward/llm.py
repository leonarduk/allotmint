"""One model call at a time for the data steward, on the chat assistant's provider layer.

The chat loop (``backend.chat.providers.run_configured_chat_turn``) runs a whole
turn and returns only the final text. The steward needs more control: a per-issue
tool budget, every tool call and result recorded as evidence, and token totals. So
it drives the loop itself (``backend.data_steward.runner``) and only asks these
adapters for one completion. They reuse the chat layer's provider choice, defaults
and Bedrock client and retry policy.

Messages use one neutral shape, converted per provider:

* ``{"role": "system" | "user", "content": str}``
* ``{"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}``
* ``{"role": "tool", "tool_call_id": str, "content": str, "is_error": bool}``
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

import httpx

from backend.chat.bedrock_agent import _bedrock_client, _converse_with_retry
from backend.chat.openai_compat_agent import REQUEST_TIMEOUT_SECONDS, _parse_tool_arguments
from backend.chat.providers import OPENAI_COMPAT_DEFAULTS, resolve_chat_provider
from backend.config import Config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMReply:
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class StewardLLM(Protocol):
    async def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        """One completion. ``tools`` are ``{name, description, input_schema}`` dicts."""


class OpenAICompatLLM:
    """Ollama / DeepSeek, via ``POST {base_url}/chat/completions``."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, model: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model

    @staticmethod
    def _message(message: Dict[str, Any]) -> Dict[str, Any]:
        if message["role"] == "tool":
            return {"role": "tool", "tool_call_id": message["tool_call_id"], "content": message["content"]}
        if message["role"] == "assistant" and message.get("tool_calls"):
            return {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in message["tool_calls"]
                ],
            }
        return {"role": message["role"], "content": message.get("content") or ""}

    async def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        body: Dict[str, Any] = {"model": self._model, "messages": [self._message(m) for m in messages]}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description") or tool["name"],
                        "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                    },
                }
                for tool in tools
            ]
        response = await self._client.post(self._url, json=body)
        response.raise_for_status()
        payload = response.json()
        output = payload["choices"][0]["message"]
        usage = payload.get("usage") or {}
        return LLMReply(
            content=output.get("content") or "",
            tool_calls=[
                ToolCall(
                    id=call.get("id") or f"call_{index}",
                    name=call["function"]["name"],
                    arguments=_parse_tool_arguments(call["function"].get("arguments")),
                )
                for index, call in enumerate(output.get("tool_calls") or [])
            ],
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )


def to_bedrock_messages(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return ``(system, messages)`` for the Converse API.

    Tool results and any user text after them become one user message (tool
    results first), since Converse needs strict user/assistant alternation.
    """

    system: List[Dict[str, Any]] = []
    converted: List[Dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "system":
            system.append({"text": message["content"]})
            continue
        if role == "assistant":
            content: List[Dict[str, Any]] = [{"text": message["content"]}] if message.get("content") else []
            content.extend(
                {"toolUse": {"toolUseId": call.id, "name": call.name, "input": call.arguments}}
                for call in message.get("tool_calls") or []
            )
            converted.append({"role": "assistant", "content": content or [{"text": "(no text)"}]})
            continue
        block = _bedrock_user_block(message)
        if converted and converted[-1]["role"] == "user":
            converted[-1]["content"].append(block)
        else:
            converted.append({"role": "user", "content": [block]})
    return system, converted


def _bedrock_user_block(message: Dict[str, Any]) -> Dict[str, Any]:
    if message["role"] != "tool":
        return {"text": message["content"]}
    return {
        "toolResult": {
            "toolUseId": message["tool_call_id"],
            "content": [{"text": message["content"]}],
            "status": "error" if message.get("is_error") else "success",
        }
    }


class BedrockLLM:
    """Bedrock Converse, with the chat assistant's client and retry policy."""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    async def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        system, converted = to_bedrock_messages(messages)
        kwargs: Dict[str, Any] = {"modelId": self._model_id, "messages": converted}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool["name"],
                            "description": tool.get("description") or tool["name"],
                            "inputSchema": {"json": tool.get("input_schema") or {"type": "object"}},
                        }
                    }
                    for tool in tools
                ]
            }
        response = await _converse_with_retry(_bedrock_client(), **kwargs)
        blocks = response["output"]["message"]["content"]
        usage = response.get("usage") or {}
        return LLMReply(
            content="\n".join(block["text"] for block in blocks if "text" in block),
            tool_calls=[
                ToolCall(
                    id=block["toolUse"]["toolUseId"],
                    name=block["toolUse"]["name"],
                    arguments=block["toolUse"].get("input") or {},
                )
                for block in blocks
                if "toolUse" in block
            ],
            input_tokens=int(usage.get("inputTokens") or 0),
            output_tokens=int(usage.get("outputTokens") or 0),
        )


@dataclass
class ProviderChoice:
    provider: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None


def resolve_provider(cfg: Config) -> ProviderChoice:
    """The chat assistant's provider and model (CHAT_PROVIDER / CHAT_MODEL / CHAT_BASE_URL)."""

    provider = resolve_chat_provider(cfg)
    if provider == "bedrock":
        return ProviderChoice(provider=provider, model=cfg.bedrock_model_id)
    default_base_url, default_model = OPENAI_COMPAT_DEFAULTS[provider]
    api_key = os.getenv("DEEPSEEK_API_KEY") if provider == "deepseek" else None
    if provider == "deepseek" and not api_key:
        raise RuntimeError("CHAT_PROVIDER=deepseek requires DEEPSEEK_API_KEY")
    return ProviderChoice(
        provider=provider,
        model=cfg.chat_model or default_model,
        base_url=cfg.chat_base_url or default_base_url,
        api_key=api_key,
    )


def new_http_client(choice: ProviderChoice) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {choice.api_key}"} if choice.api_key else {}
    return httpx.AsyncClient(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)


# USD per million (input, output) tokens. Ollama runs locally at no cost; a model
# missing here records cost_usd as null rather than a guess. DATA_STEWARD_COST_PER_MTOK
# ("<input>,<output>") overrides it for any provider.
_PRICES_PER_MTOK: Dict[str, Tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}


def _override_rates() -> Optional[Tuple[float, float]]:
    """``DATA_STEWARD_COST_PER_MTOK`` as (input, output) rates; None when unset or malformed.

    A malformed value is logged and ignored rather than raised: it runs after the
    investigations, so raising would throw away a finished run's items and totals.
    """

    override = os.getenv("DATA_STEWARD_COST_PER_MTOK", "").strip()
    if not override:
        return None
    rate_in, _, rate_out = override.partition(",")
    try:
        return float(rate_in), float(rate_out or rate_in)
    except ValueError:
        logger.warning(
            "Ignoring malformed DATA_STEWARD_COST_PER_MTOK %s (expected '<input>,<output>' USD per million tokens)",
            sanitise_log_value(override),
        )
        return None


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    rates = _override_rates()
    if rates is None and provider == "ollama":
        return 0.0
    if rates is None:
        rates = _PRICES_PER_MTOK.get(model)
    if rates is None:
        return None
    return round((input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000, 6)
