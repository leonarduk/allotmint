"""Tests for create_followup_issues.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_followup_issues", SCRIPTS_DIR / "create_followup_issues.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._data = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


def test_generate_body_returns_fallback_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = mod._build_body("Fix the thing", "42", "Some review text")
    assert "PR #42" in body
    assert "Follow-up" in body


def test_generate_body_calls_claude_and_returns_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_payload = {"content": [{"text": "## What\nFix the thing\n\n_Follow-up from AI review of PR #42._"}]}
    monkeypatch.setattr(
        mod.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(fake_payload),
    )
    body = mod._generate_body_via_claude("Fix the thing", "42", "Review text here")
    assert "Fix the thing" in body
    assert "Follow-up" in body


def test_generate_body_falls_back_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = load_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def raise_error(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://example.test", code=500, msg="server error", hdrs=None, fp=None
        )

    monkeypatch.setattr(mod.urllib.request, "urlopen", raise_error)
    body = mod._generate_body_via_claude("Fix the thing", "42", "Review text here")
    assert "PR #42" in body
    assert "failed to generate" in capsys.readouterr().err


def test_build_body_uses_fallback_when_no_review_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    body = mod._build_body("Fix the thing", "99", None)
    assert "PR #99" in body


def test_main_missing_review_file_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = load_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    followups = tmp_path / "followups.json"
    followups.write_text(json.dumps([]))

    monkeypatch.setattr(
        sys, "argv", [
            "create_followup_issues.py",
            str(followups),
            "7",
            "/nonexistent/review.md",
        ]
    )
    result = mod.main()
    assert result == 0
    assert "WARNING: review file not found" in capsys.readouterr().err


def test_main_wrong_arg_count_prints_usage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = load_module()
    monkeypatch.setattr(sys, "argv", ["create_followup_issues.py"])
    assert mod.main() == 1
    assert "Usage:" in capsys.readouterr().err


def test_create_issues_skips_empty_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    calls: list[list[str]] = []

    monkeypatch.setattr(mod, "issue_exists", lambda title: False)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(cmd),
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    mod.create_issues(["", "  ", "Real title"], "5", None)
    assert len(calls) == 1
    assert "Real title" in calls[0]


def test_create_issues_skips_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    calls: list = []

    monkeypatch.setattr(mod, "issue_exists", lambda title: True)
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))

    mod.create_issues(["Already exists"], "5", None)
    assert calls == []


def test_create_issues_passes_generated_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    created: list[list[str]] = []

    monkeypatch.setattr(mod, "issue_exists", lambda title: False)
    monkeypatch.setattr(mod, "_build_body", lambda *args, **kwargs: "Rich body content")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda cmd, **kwargs: created.append(cmd),
    )

    mod.create_issues(["My title"], "10", "review text")
    assert created
    body_idx = created[0].index("--body") + 1
    assert created[0][body_idx] == "Rich body content"


@pytest.mark.parametrize(
    ("body", "expected_label"),
    [
        ("**LLM tier**\n**Haiku** — simple task", "haiku"),
        ("**LLM tier**\n**Sonnet** — moderate reasoning", "sonnet"),
        ("**LLM tier**\n**Opus** — complex design", "opus"),
        ("**LLM tier**\n**local-7b** — simple mechanical change", "local-7b"),
        ("**LLM tier**\n**local-14b** — moderate reasoning task", "local-14b"),
        ("Use Haiku for this", "haiku"),
        ("Use Sonnet here", "sonnet"),
        ("Requires Opus", "opus"),
        ("Suitable for local-7b", "local-7b"),
        ("Recommend local-14b for this", "local-14b"),
        ("No model mentioned", None),
    ],
)
def test_extract_llm_label(body: str, expected_label: str | None) -> None:
    mod = load_module()
    assert mod._extract_llm_label(body) == expected_label


def test_create_issues_applies_llm_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_module()
    created: list[list[str]] = []

    monkeypatch.setattr(mod, "issue_exists", lambda title: False)
    monkeypatch.setattr(
        mod, "_build_body", lambda *args, **kwargs: "**LLM tier**\n**Sonnet** — moderate"
    )
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kwargs: created.append(cmd))

    mod.create_issues(["My title"], "10", "review text")
    assert created
    assert "--label" in created[0]
    assert "sonnet" in created[0]
    assert "ai-suggested" in created[0]


def test_create_issues_applies_no_llm_label_when_body_has_no_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the generated body contains no LLM tier mention, create_issues()
    should apply only the generic 'ai-suggested' label and no model-tier label
    (haiku/sonnet/opus). The tier label is derived from body content only;
    there is no automatic fallback to a model-name-derived tier."""
    mod = load_module()
    created: list[list[str]] = []

    monkeypatch.setattr(mod, "issue_exists", lambda title: False)
    monkeypatch.setattr(mod, "_build_body", lambda *args, **kwargs: "No model info here.")
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kwargs: created.append(cmd))

    mod.create_issues(["My title"], "10", None)
    assert created
    assert "ai-suggested" in created[0]
    label_values = [created[0][i + 1] for i, v in enumerate(created[0][:-1]) if v == "--label"]
    assert not any(t in label_values for t in ("haiku", "sonnet", "opus"))
