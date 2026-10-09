from dataclasses import replace

import pytest

from backend.chat import providers
from backend.config import config


def _cfg(**overrides):
    return replace(config, **overrides)


@pytest.mark.parametrize(
    ("chat_provider", "app_env", "expected"),
    [
        (None, "local", "ollama"),
        (None, "aws", "bedrock"),
        (None, "production", "bedrock"),
        (None, None, "bedrock"),
        ("deepseek", "aws", "deepseek"),
        ("bedrock", "local", "bedrock"),
    ],
)
def test_resolve_chat_provider(chat_provider, app_env, expected):
    assert providers.resolve_chat_provider(_cfg(chat_provider=chat_provider, app_env=app_env)) == expected


async def test_bedrock_provider_uses_bedrock_agent(monkeypatch):
    captured = {}

    async def fake_bedrock(
        message,
        history,
        *,
        mcp_server_url,
        bedrock_model_id,
        local_tools=None,
        system_prompt=None,
        allowed_tools=None,
    ):
        captured.update(message=message, mcp_server_url=mcp_server_url, bedrock_model_id=bedrock_model_id)
        return "from bedrock"

    monkeypatch.setattr(providers.bedrock_agent, "run_chat_turn", fake_bedrock)

    reply = await providers.run_configured_chat_turn(
        "hi",
        [],
        cfg=_cfg(chat_provider="bedrock", bedrock_model_id="amazon.nova-lite-v1:0"),
        mcp_server_url="https://example.com/mcp",
    )

    assert reply == "from bedrock"
    assert captured == {
        "message": "hi",
        "mcp_server_url": "https://example.com/mcp",
        "bedrock_model_id": "amazon.nova-lite-v1:0",
    }


@pytest.mark.parametrize(
    ("provider", "chat_model", "chat_base_url", "env_key", "expected"),
    [
        ("ollama", None, None, None, ("http://localhost:11434/v1", "qwen3.5:9b", None)),
        ("ollama", "llama3.2", "http://gpu-box:11434/v1", None, ("http://gpu-box:11434/v1", "llama3.2", None)),
        ("deepseek", None, None, "sk-test", ("https://api.deepseek.com/v1", "deepseek-chat", "sk-test")),
    ],
)
async def test_openai_compat_providers_resolve_base_url_model_and_key(
    monkeypatch, provider, chat_model, chat_base_url, env_key, expected
):
    if env_key:
        monkeypatch.setenv("DEEPSEEK_API_KEY", env_key)
    else:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    captured = {}

    async def fake_openai(
        message,
        history,
        *,
        mcp_server_url,
        base_url,
        model,
        api_key=None,
        local_tools=None,
        system_prompt=None,
        allowed_tools=None,
    ):
        captured["args"] = (base_url, model, api_key)
        return "from openai-compat"

    monkeypatch.setattr(providers.openai_compat_agent, "run_chat_turn", fake_openai)

    reply = await providers.run_configured_chat_turn(
        "hi",
        [],
        cfg=_cfg(chat_provider=provider, chat_model=chat_model, chat_base_url=chat_base_url),
        mcp_server_url="http://localhost:8001/mcp",
    )

    assert reply == "from openai-compat"
    assert captured["args"] == expected


async def test_deepseek_without_api_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        await providers.run_configured_chat_turn(
            "hi", [], cfg=_cfg(chat_provider="deepseek"), mcp_server_url="http://localhost:8001/mcp"
        )
