"""Tests for .github/scripts/llm_labels.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("llm_labels", SCRIPTS_DIR / "llm_labels.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("body", "expected_label"),
    [
        ("**LLM tier**\n**Haiku** — simple task", "haiku"),
        ("**LLM tier**\n**Sonnet** — moderate reasoning", "sonnet"),
        ("**LLM tier**\n**Opus** — complex design", "opus"),
        ("**LLM tier**\n**local-7b** — simple mechanical change", "local-7b"),
        ("**LLM tier**\n**local-14b** — moderate reasoning task", "local-14b"),
        ("**llm tier**\n**SONNET** — case insensitive", "sonnet"),
        ("Use Haiku for this", "haiku"),
        ("Use Sonnet here", "sonnet"),
        ("Requires Opus", "opus"),
        ("Suitable for local-7b", "local-7b"),
        ("Recommend local-14b for this", "local-14b"),
        ("No model mentioned", None),
        ("", None),
    ],
)
def test_extract_tier_label(body: str, expected_label: str | None) -> None:
    mod = load_module()
    assert mod.extract_tier_label(body) == expected_label


def test_extract_tier_label_prefers_llm_tier_section_over_bare_mention() -> None:
    mod = load_module()
    body = "Mentions sonnet in passing.\n\n**LLM tier**\n**Opus** — complex design"
    assert mod.extract_tier_label(body) == "opus"


def test_extract_tier_label_with_custom_tier_map() -> None:
    mod = load_module()
    custom_map = {"fast": "fast-model", "slow": "slow-model"}
    assert mod.extract_tier_label("**LLM tier**\n**Fast** — quick task", custom_map) == "fast-model"
    assert mod.extract_tier_label("Use the slow model", custom_map) == "slow-model"
    assert mod.extract_tier_label("No tier here", custom_map) is None
    # Default tier map shouldn't match when a custom map is supplied.
    assert mod.extract_tier_label("**LLM tier**\n**Sonnet** — moderate", custom_map) is None


def test_extract_tier_label_handles_multiple_mentions() -> None:
    mod = load_module()
    body = "This could use haiku or sonnet, but **LLM tier**\n**Opus** — complex"
    assert mod.extract_tier_label(body) == "opus"


@pytest.mark.parametrize(
    ("model_name", "expected_label"),
    [
        ("claude-haiku-4-5-20251001", "haiku"),
        ("claude-sonnet-4-6", "sonnet"),
        ("claude-opus-4-8", "opus"),
        ("local-7b-instruct", "local-7b"),
        ("local-14b-instruct", "local-14b"),
        ("qwen2.5-14b-instruct", "local-14b"),
        ("qwen2.5-7b-instruct", "local-7b"),
        ("some-unrecognised-model", "sonnet"),
        ("", "sonnet"),
    ],
)
def test_get_fallback_tier_label(model_name: str, expected_label: str) -> None:
    mod = load_module()
    assert mod.get_fallback_tier_label(model_name) == expected_label


def test_get_fallback_tier_label_with_custom_tier_map() -> None:
    mod = load_module()
    custom_map = {"fast": "fast-model", "slow": "slow-model"}
    assert mod.get_fallback_tier_label("the-fast-one", custom_map) == "fast-model"
    assert mod.get_fallback_tier_label("the-slow-one", custom_map) == "slow-model"
    # No match and no recognised tiers in the custom map -> default.
    assert mod.get_fallback_tier_label("unrelated-model", custom_map) == "sonnet"


def test_llm_tier_map_is_stable() -> None:
    mod = load_module()
    assert mod.LLM_TIER_MAP == {
        "local-7b": "local-7b",
        "local-14b": "local-14b",
        "haiku": "haiku",
        "sonnet": "sonnet",
        "opus": "opus",
    }
