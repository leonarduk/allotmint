"""Pick the LLM behind POST /chat from config and run one turn through it."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from backend.chat import bedrock_agent, openai_compat_agent
from backend.chat.local_tools import LocalTools
from backend.chat.turn_limits import TurnLimits
from backend.config import Config

# (base_url, model) used when chat_base_url / chat_model are unset.
OPENAI_COMPAT_DEFAULTS: Dict[str, Tuple[str, str]] = {
    "ollama": ("http://localhost:11434/v1", "qwen3.5:9b"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
}


def resolve_chat_provider(cfg: Config) -> str:
    """Return the configured provider, defaulting to Ollama only for local runs.

    Anything other than ``app_env == "local"`` (AWS, production, unset)
    keeps Bedrock so a deployment never silently switches provider.
    """

    if cfg.chat_provider:
        return cfg.chat_provider
    return "ollama" if cfg.app_env == "local" else "bedrock"


async def run_configured_chat_turn(
    message: str,
    history: List[Dict[str, str]],
    *,
    cfg: Config,
    mcp_server_url: str,
    local_tools: Optional[LocalTools] = None,
    system_prompt: Optional[str] = None,
    limits: Optional[TurnLimits] = None,
) -> str:
    provider = resolve_chat_provider(cfg)
    # Only passed when set, so the interactive chat's call is unchanged.
    extra = {"limits": limits} if limits is not None else {}
    if provider == "bedrock":
        return await bedrock_agent.run_chat_turn(
            message,
            history,
            mcp_server_url=mcp_server_url,
            bedrock_model_id=cfg.bedrock_model_id,
            local_tools=local_tools,
            system_prompt=system_prompt,
            **extra,
        )

    default_base_url, default_model = OPENAI_COMPAT_DEFAULTS[provider]
    api_key = os.getenv("DEEPSEEK_API_KEY") if provider == "deepseek" else None
    if provider == "deepseek" and not api_key:
        raise RuntimeError("CHAT_PROVIDER=deepseek requires DEEPSEEK_API_KEY")
    return await openai_compat_agent.run_chat_turn(
        message,
        history,
        mcp_server_url=mcp_server_url,
        base_url=cfg.chat_base_url or default_base_url,
        model=cfg.chat_model or default_model,
        api_key=api_key,
        local_tools=local_tools,
        system_prompt=system_prompt,
        **extra,
    )
