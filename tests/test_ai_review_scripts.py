from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import review_common  # noqa: E402


def load_script_module(module_name: str, file_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict[str, object] | bytes, raw: bool = False) -> None:
        self._payload = payload if raw else json.dumps(payload).encode()

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
    monkeypatch.setattr(review_common.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(payload))

    assert module.main() == 0
    assert "Looks good" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "payload", "expected_err"),
    [
        (
            "gpt_review_empty_choices",
            "gpt_review.py",
            "OPENAI_API_KEY",
            {"choices": []},
            "ERROR: OpenAI API returned an empty review",
        ),
        (
            "gpt_review_empty_content",
            "gpt_review.py",
            "OPENAI_API_KEY",
            {"choices": [{"message": {"content": ""}}]},
            "ERROR: OpenAI API returned an empty review",
        ),
        (
            "claude_review_empty_content",
            "claude_review.py",
            "ANTHROPIC_API_KEY",
            {"content": []},
            "ERROR: Claude API returned an empty review",
        ),
    ],
)
def test_review_script_exits_on_empty_api_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    file_name: str,
    api_env: str,
    payload: dict[str, object],
    expected_err: str,
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setattr(review_common.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(payload))

    assert module.main() == 1
    assert expected_err in capsys.readouterr().err


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

    monkeypatch.setattr(review_common.urllib.request, "urlopen", raise_http_error)

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    assert expected_message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "expected_message"),
    [
        (
            "gpt_review_url_error",
            "gpt_review.py",
            "OPENAI_API_KEY",
            "ERROR: OpenAI API request failed: timed out",
        ),
        (
            "claude_review_url_error",
            "claude_review.py",
            "ANTHROPIC_API_KEY",
            "ERROR: Claude API request failed: timed out",
        ),
    ],
)
def test_review_script_reports_mocked_url_error(
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

    def raise_url_error(*args, **kwargs):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(review_common.urllib.request, "urlopen", raise_url_error)

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    assert expected_message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env", "expected_message"),
    [
        (
            "gpt_review_bad_json",
            "gpt_review.py",
            "OPENAI_API_KEY",
            "ERROR: OpenAI API returned non-JSON response",
        ),
        (
            "claude_review_bad_json",
            "claude_review.py",
            "ANTHROPIC_API_KEY",
            "ERROR: Claude API returned non-JSON response",
        ),
    ],
)
def test_review_script_reports_mocked_non_json_response(
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
    monkeypatch.setattr(
        review_common.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b"<html>not json</html>", raw=True),
    )

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    assert expected_message in capsys.readouterr().err


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_default_globs_include_codeowners_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script_module("prepare_review_diff", "prepare_review_diff.py")

    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-b", "main"], repo)
    _run_git(["config", "user.email", "test@example.com"], repo)
    _run_git(["config", "user.name", "Test"], repo)

    (repo / "README.md").write_text("hello\n")
    _run_git(["add", "README.md"], repo)
    _run_git(["commit", "-m", "init"], repo)
    _run_git(["update-ref", "refs/remotes/origin/main", "HEAD"], repo)

    github_dir = repo / ".github"
    github_dir.mkdir()
    (github_dir / "CODEOWNERS").write_text("/backend/ @leonarduk\n")
    _run_git(["add", ".github/CODEOWNERS"], repo)
    _run_git(["commit", "-m", "add codeowners"], repo)

    monkeypatch.chdir(repo)
    diff = module.git_diff("main", module.DEFAULT_GLOBS)

    assert ".github/CODEOWNERS" in diff
