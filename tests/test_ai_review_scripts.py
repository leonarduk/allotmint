"""Tests for AI review scripts and shared helpers."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("cicaid_devtools", reason="private review tooling is not installed")

import cicaid_devtools.lib.review_common as review_common  # noqa: E402
from cicaid_devtools.lib.review_common import ProviderOutageError  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_script_module(module_name: str, file_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name,
        SCRIPTS_DIR / file_name,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict | bytes, raw: bool = False) -> None:
        self._payload = payload if raw else json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


# ----------------------------------------------------------- model resolution


def test_claude_review_uses_current_default_model_and_allows_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module("claude_review_model", "claude_review.py")
    assert module.get_anthropic_model() == "claude-sonnet-4-6"
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    assert module.get_anthropic_model() == "claude-sonnet-4-5"


def test_deepseek_review_uses_current_default_model_and_allows_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cicaid_devtools.lib.deepseek_review import get_deepseek_model

    assert get_deepseek_model() == "deepseek-v4-flash"
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    assert get_deepseek_model() == "deepseek-reasoner"
    monkeypatch.setenv("DEEPSEEK_MODEL", "")
    assert get_deepseek_model() == "deepseek-v4-flash"


# ---------------------------------------------------------- thinking-mode guard


def test_deepseek_review_disables_thinking_mode_for_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for #5697: flash-tier reviews must disable thinking."""
    module = load_script_module(
        "deepseek_review_thinking_flash",
        "deepseek_review.py",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    captured_payloads: list[dict] = []

    def fake_urlopen(request, *args, **kwargs):
        captured_payloads.append(json.loads(request.data.decode()))
        return FakeResponse(
            {
                "choices": [{"message": {"content": "Looks good\n**APPROVE**"}}],
            }
        )

    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        fake_urlopen,
    )
    assert module.main() == 0
    assert captured_payloads[0]["thinking"] == {"type": "disabled"}


def test_deepseek_review_leaves_thinking_mode_enabled_for_reasoner_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module(
        "deepseek_review_thinking_reasoner",
        "deepseek_review.py",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    captured_payloads: list[dict] = []

    def fake_urlopen(request, *args, **kwargs):
        captured_payloads.append(json.loads(request.data.decode()))
        return FakeResponse(
            {
                "choices": [{"message": {"content": "Looks good\n**APPROVE**"}}],
            }
        )

    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        fake_urlopen,
    )
    assert module.main() == 0
    assert "thinking" not in captured_payloads[0]


def test_deepseek_review_warns_when_only_reasoning_content_returned(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_script_module(
        "deepseek_review_reasoning_only",
        "deepseek_review.py",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    payload = {
        "choices": [
            {
                "message": {"content": "", "reasoning_content": "thinking…"},
                "finish_reason": "length",
            }
        ],
    }
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        lambda *a, **kw: FakeResponse(payload),
    )
    # The package's finalize_review soft-skips an empty review (returns 0).
    assert module.main() == 0
    output = capsys.readouterr().out
    assert "EMPTY PROVIDER RESPONSE" in output


# --------------------------------------------------------------- missing key


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env"),
    [
        ("gpt_review_test", "gpt_review.py", "OPENAI_API_KEY"),
        ("claude_review_test", "claude_review.py", "ANTHROPIC_API_KEY"),
        ("deepseek_review_test", "deepseek_review.py", "DEEPSEEK_API_KEY"),
    ],
)
def test_review_script_emits_missing_key_notice_when_key_not_set(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.delenv(api_env, raising=False)
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n")

    assert module.main() == 0
    assert "API KEY NOT CONFIGURED" in capsys.readouterr().out


# -------------------------------------------------------------- empty diff


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "provider_name"),
    [
        ("gpt_review_empty", "gpt_review.py", "OPENAI_API_KEY", "GPT"),
        ("claude_review_empty", "claude_review.py", "ANTHROPIC_API_KEY", "Claude"),
        ("deepseek_review_empty", "deepseek_review.py", "DEEPSEEK_API_KEY", "DeepSeek"),
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
    assert "EMPTY DIFF" in capsys.readouterr().out


# ---------------------------------------------------------- successful review


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
        (
            "deepseek_review_success",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            {"choices": [{"message": {"content": "Looks good\n**APPROVE**"}}]},
        ),
    ],
)
def test_review_script_prints_review_on_mocked_api_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
    payload: dict,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        lambda *a, **kw: FakeResponse(payload),
    )
    assert module.main() == 0
    assert "Looks good" in capsys.readouterr().out


# ----------------------------------------------------- discussion in prompt


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "payload"),
    [
        (
            "gpt_review_discussion",
            "gpt_review.py",
            "OPENAI_API_KEY",
            {"choices": [{"message": {"content": "Looks good\n**APPROVE**"}}]},
        ),
        (
            "claude_review_discussion",
            "claude_review.py",
            "ANTHROPIC_API_KEY",
            {"content": [{"type": "text", "text": "Looks good\n**APPROVE**"}]},
        ),
        (
            "deepseek_review_discussion",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            {"choices": [{"message": {"content": "Looks good\n**APPROVE**"}}]},
        ),
    ],
)
def test_review_script_includes_discussion_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    file_name: str,
    api_env: str,
    payload: dict,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setenv(
        "DISCUSSION",
        "[2024-01-01T00:00:00Z] alice: please re-check the null check",
    )

    captured_payloads: list[dict] = []

    def fake_urlopen(request, *args, **kwargs):
        captured_payloads.append(json.loads(request.data.decode()))
        return FakeResponse(payload)

    monkeypatch.setattr(review_common.urllib.request, "urlopen", fake_urlopen)
    assert module.main() == 0
    prompt = json.dumps(captured_payloads[0])
    assert "Discussion since your last review" in prompt
    assert "please re-check the null check" in prompt


# ------------------------------------------------------ empty API response


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "payload"),
    [
        (
            "gpt_review_empty_choices",
            "gpt_review.py",
            "OPENAI_API_KEY",
            {"choices": []},
        ),
        (
            "gpt_review_empty_content",
            "gpt_review.py",
            "OPENAI_API_KEY",
            {"choices": [{"message": {"content": ""}}]},
        ),
        (
            "claude_review_empty_content",
            "claude_review.py",
            "ANTHROPIC_API_KEY",
            {"content": []},
        ),
        (
            "deepseek_review_empty_choices",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            {"choices": []},
        ),
        (
            "deepseek_review_empty_content",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            {"choices": [{"message": {"content": ""}}]},
        ),
    ],
)
def test_review_script_soft_skips_on_empty_api_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
    payload: dict,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        lambda *a, **kw: FakeResponse(payload),
    )
    assert module.main() == 0
    assert "EMPTY PROVIDER RESPONSE" in capsys.readouterr().out


# ------------------------------------------------------- HTTP 500 / outage


def _raise_fake_500(*args, **kwargs):
    raise urllib.error.HTTPError(
        url="https://example.test",
        code=500,
        msg="server error",
        hdrs=None,
        fp=io.BytesIO(b"upstream broke"),
    )


def _disabled_test_claude_and_gpt_raise_provider_outage_on_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude/GPT don't catch ProviderOutageError internally."""
    for file_name, api_env in [
        ("claude_review.py", "ANTHROPIC_API_KEY"),
        ("gpt_review.py", "OPENAI_API_KEY"),
    ]:
        module = load_script_module(f"test_{file_name}", file_name)
        monkeypatch.setenv(api_env, "test-key")
        monkeypatch.setenv("PR_TITLE", "Add thing")
        monkeypatch.setenv("ISSUE_BODY", "Do thing")
        monkeypatch.setenv(
            "DIFF",
            "diff --git a/a.py b/a.py\n+print('hi')\n",
        )
        monkeypatch.setattr(
            review_common.urllib.request,
            "urlopen",
            _raise_fake_500,
        )
        with pytest.raises(ProviderOutageError):
            module.main()


def test_deepseek_handles_500_as_soft_skip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DeepSeek catches ProviderOutageError and emits soft-fail notice."""
    module = load_script_module(
        "deepseek_review_500",
        "deepseek_review.py",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        _raise_fake_500,
    )
    assert module.main() == 0
    assert "PROVIDER OUTAGE" in capsys.readouterr().out


# ---------------------------------------------------- URL error / timeout


def _raise_url_error(*args, **kwargs):
    raise urllib.error.URLError("timed out")


def _disabled_test_claude_and_gpt_raise_provider_outage_on_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for file_name, api_env in [
        ("claude_review.py", "ANTHROPIC_API_KEY"),
        ("gpt_review.py", "OPENAI_API_KEY"),
    ]:
        module = load_script_module(f"test_url_{file_name}", file_name)
        monkeypatch.setenv(api_env, "test-key")
        monkeypatch.setenv("PR_TITLE", "Add thing")
        monkeypatch.setenv("ISSUE_BODY", "Do thing")
        monkeypatch.setenv(
            "DIFF",
            "diff --git a/a.py b/a.py\n+print('hi')\n",
        )
        monkeypatch.setattr(
            review_common.urllib.request,
            "urlopen",
            _raise_url_error,
        )
        with pytest.raises(ProviderOutageError):
            module.main()


def test_deepseek_handles_url_error_as_soft_skip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_script_module(
        "deepseek_review_url_error",
        "deepseek_review.py",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        _raise_url_error,
    )
    assert module.main() == 0
    assert "PROVIDER OUTAGE" in capsys.readouterr().out


# ------------------------------------------------- non-JSON response


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env"),
    [
        ("gpt_review_bad_json", "gpt_review.py", "OPENAI_API_KEY"),
        ("claude_review_bad_json", "claude_review.py", "ANTHROPIC_API_KEY"),
        ("deepseek_review_bad_json", "deepseek_review.py", "DEEPSEEK_API_KEY"),
    ],
)
def test_review_script_reports_mocked_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    file_name: str,
    api_env: str,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        lambda *a, **kw: FakeResponse(b"<html>not json</html>", raw=True),
    )
    with pytest.raises(SystemExit):
        module.main()


# ---------------------------------------------------- filter_binary_files


class TestFilterBinaryFiles:
    def test_empty_diff(self) -> None:
        assert review_common.filter_binary_files("") == ""

    def test_text_only_diff_is_unchanged(self) -> None:
        diff = "diff --git a/file.py b/file.py\n" "--- a/file.py\n+++ b/file.py\n" "@@ -1 +1 @@\n-old\n+new\n"
        assert review_common.filter_binary_files(diff) == diff

    def test_binary_only_diff_becomes_empty(self) -> None:
        diff = "diff --git a/logo.png b/logo.png\n" "Binary files a/logo.png and b/logo.png differ\n"
        assert review_common.filter_binary_files(diff) == ""

    def test_mixed_diff_keeps_only_text_files(self) -> None:
        diff = (
            "diff --git a/logo.png b/logo.png\n"
            "Binary files a/logo.png and b/logo.png differ\n"
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n+++ b/file.py\n"
            "@@ -1 +1 @@\n-old\n+new\n"
        )
        filtered = review_common.filter_binary_files(diff)
        assert "logo.png" not in filtered
        assert "file.py" in filtered
        assert "+new" in filtered

    def test_git_binary_patch_form_is_also_filtered(self) -> None:
        diff = "diff --git a/data.bin b/data.bin\n" "GIT binary patch\nliteral 10\n...\n"
        assert review_common.filter_binary_files(diff) == ""

    def test_renamed_binary_file_is_filtered(self) -> None:
        diff = (
            "diff --git a/old.png b/new.png\n"
            "similarity index 100%\n"
            "rename from old.png\n"
            "rename to new.png\n"
            "Binary files a/old.png and b/new.png differ\n"
        )
        assert review_common.filter_binary_files(diff) == ""


# --- Replacement tests for disabled loop-based tests above ---


def test_claude_raises_provider_outage_on_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude wrapper's own main() doesn't catch ProviderOutageError."""
    module = load_script_module("claude_review_500", "claude_review.py")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        _raise_fake_500,
    )
    with pytest.raises(ProviderOutageError):
        module.main()


def test_gpt_handles_500_as_soft_skip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GPT wrapper delegates to package main() which catches ProviderOutageError."""
    module = load_script_module("gpt_review_500", "gpt_review.py")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        _raise_fake_500,
    )
    assert module.main() == 0
    assert "PROVIDER OUTAGE" in capsys.readouterr().out


def test_claude_raises_provider_outage_on_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module("claude_review_url", "claude_review.py")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        _raise_url_error,
    )
    with pytest.raises(ProviderOutageError):
        module.main()


def test_gpt_handles_url_error_as_soft_skip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_script_module("gpt_review_url", "gpt_review.py")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        _raise_url_error,
    )
    assert module.main() == 0
    assert "PROVIDER OUTAGE" in capsys.readouterr().out
