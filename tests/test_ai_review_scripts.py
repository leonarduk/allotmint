from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
import urllib.error

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_script_module(module_name: str, file_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_claude_review_uses_current_default_model_and_allows_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module("claude_review_model", "claude_review.py")

    assert module.get_anthropic_model() == "claude-sonnet-4-6"

    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    assert module.get_anthropic_model() == "claude-sonnet-4-5"


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env"),
    [
        ("gpt_review_test", "gpt_review.py", "OPENAI_API_KEY"),
        ("claude_review_test", "claude_review.py", "ANTHROPIC_API_KEY"),
    ],
)
def test_review_script_exits_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.delenv(api_env, raising=False)
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n")

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    assert f"ERROR: {api_env} not set" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "provider_name"),
    [
        ("gpt_review_empty", "gpt_review.py", "OPENAI_API_KEY", "GPT"),
        ("claude_review_empty", "claude_review.py", "ANTHROPIC_API_KEY", "Claude"),
    ],
)
def test_review_script_exits_cleanly_on_empty_diff(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
    provider_name: str,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("DIFF", "   \n")

    assert module.main() == 0
    assert f"No {provider_name} review generated because the filtered diff was empty." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "payload"),
    [
        (
            "gpt_review_success",
            "gpt_review.py",
            "OPENAI_API_KEY",
            {"choices": [{"message": {"content": "Looks good\n**APPROVE**"}}]},
        ),
        (
            "claude_review_success",
            "claude_review.py",
            "ANTHROPIC_API_KEY",
            {"content": [{"type": "text", "text": "Looks good\n**APPROVE**"}]},
        ),
    ],
)
def test_review_script_prints_review_on_mocked_api_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
    payload: dict[str, object],
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(payload))

    assert module.main() == 0
    assert "Looks good" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "expected_message"),
    [
        ("gpt_review_failure", "gpt_review.py", "OPENAI_API_KEY", "ERROR: OpenAI API returned 500: upstream broke"),
        ("claude_review_failure", "claude_review.py", "ANTHROPIC_API_KEY", "ERROR: Claude API returned 500: upstream broke"),
    ],
)
def test_review_script_reports_mocked_api_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
    expected_message: str,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")

    def raise_http_error(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://example.test",
            code=500,
            msg="server error",
            hdrs=None,
            fp=io.BytesIO(b"upstream broke"),
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", raise_http_error)

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    assert expected_message in capsys.readouterr().err
