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


def test_deepseek_review_uses_current_default_model_and_allows_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module("deepseek_review_model", "deepseek_review.py")

    assert module.get_deepseek_model() == "deepseek-chat"

    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    assert module.get_deepseek_model() == "deepseek-reasoner"

    # An empty override (e.g. an unset workflow input) falls back to the default
    # rather than sending an empty model string to the API.
    monkeypatch.setenv("DEEPSEEK_MODEL", "")
    assert module.get_deepseek_model() == "deepseek-chat"


@pytest.mark.parametrize(
    ("module_name", "file_name", "api_env"),
    [
        ("gpt_review_test", "gpt_review.py", "OPENAI_API_KEY"),
        ("claude_review_test", "claude_review.py", "ANTHROPIC_API_KEY"),
        ("deepseek_review_test", "deepseek_review.py", "DEEPSEEK_API_KEY"),
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
    payload: dict[str, object],
) -> None:
    module = load_script_module(module_name, file_name)
    monkeypatch.setenv(api_env, "test-key")
    monkeypatch.setenv("PR_TITLE", "Add thing")
    monkeypatch.setenv("ISSUE_BODY", "Do thing")
    monkeypatch.setenv("DIFF", "diff --git a/a.py b/a.py\n+print('hi')\n")
    monkeypatch.setenv(
        "DISCUSSION", "[2024-01-01T00:00:00Z] alice (conversation): please re-check the null check"
    )

    captured_payloads: list[dict[str, object]] = []

    def fake_urlopen(request, *args, **kwargs):
        captured_payloads.append(json.loads(request.data.decode()))
        return FakeResponse(payload)

    monkeypatch.setattr(review_common.urllib.request, "urlopen", fake_urlopen)

    assert module.main() == 0
    prompt = json.dumps(captured_payloads[0])
    assert "Discussion since your last review" in prompt
    assert "please re-check the null check" in prompt


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
        (
            "deepseek_review_empty_choices",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            {"choices": []},
            "ERROR: DeepSeek API returned an empty review",
        ),
        (
            "deepseek_review_empty_content",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            {"choices": [{"message": {"content": ""}}]},
            "ERROR: DeepSeek API returned an empty review",
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
        ("deepseek_review_failure", "deepseek_review.py", "DEEPSEEK_API_KEY", "ERROR: DeepSeek API returned 500: upstream broke"),
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
        (
            "deepseek_review_url_error",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            "ERROR: DeepSeek API request failed: timed out",
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
        (
            "deepseek_review_bad_json",
            "deepseek_review.py",
            "DEEPSEEK_API_KEY",
            "ERROR: DeepSeek API returned non-JSON response",
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


def _comment(
    login: str, body: str, created_at: str, user_type: str = "User", path: str | None = None
) -> dict:
    comment = {
        "user": {"login": login, "type": user_type},
        "body": body,
        "created_at": created_at,
    }
    if path is not None:
        comment["path"] = path
    return comment


def test_collect_discussion_returns_empty_when_no_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script_module("prepare_review_discussion", "prepare_review_discussion.py")

    monkeypatch.setattr(module, "gh_api_list", lambda path: [])

    assert module.collect_discussion("owner/repo", "1", "DeepSeek") == ""


def test_collect_discussion_filters_to_after_last_review_and_excludes_bots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module("prepare_review_discussion", "prepare_review_discussion.py")

    issue_comments = [
        _comment(
            "github-actions[bot]",
            "## DeepSeek AI Code Review\nLooks fine\n**APPROVE**",
            "2024-01-01T00:00:00Z",
            user_type="Bot",
        ),
        _comment("alice", "Old comment before the review, ignore me", "2023-12-31T00:00:00Z"),
        _comment("alice", "Addressed your concern about the null check", "2024-01-02T00:00:00Z"),
        _comment("dependabot[bot]", "Bumped a dependency", "2024-01-03T00:00:00Z", user_type="Bot"),
    ]
    inline_comments = [
        _comment(
            "alice", "Fixed the off-by-one here", "2024-01-02T12:00:00Z", path="frontend/src/foo.ts"
        ),
        _comment("bob", "Old inline comment", "2023-12-30T00:00:00Z", path="frontend/src/foo.ts"),
    ]

    def fake_gh_api_list(path: str) -> list[dict]:
        if path.startswith("repos/owner/repo/issues/"):
            return issue_comments
        return inline_comments

    monkeypatch.setattr(module, "gh_api_list", fake_gh_api_list)

    discussion = module.collect_discussion("owner/repo", "1", "DeepSeek")

    assert "Addressed your concern about the null check" in discussion
    assert "Fixed the off-by-one here" in discussion
    assert "inline on frontend/src/foo.ts" in discussion
    assert "Old comment before the review" not in discussion
    assert "Old inline comment" not in discussion
    assert "Bumped a dependency" not in discussion
    assert "AI Code Review" not in discussion


def test_collect_discussion_includes_everything_when_no_prior_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script_module("prepare_review_discussion", "prepare_review_discussion.py")

    issue_comments = [_comment("alice", "First pass discussion", "2024-01-01T00:00:00Z")]

    monkeypatch.setattr(
        module,
        "gh_api_list",
        lambda path: issue_comments if "issues" in path else [],
    )

    discussion = module.collect_discussion("owner/repo", "1", "DeepSeek")

    assert "First pass discussion" in discussion


def test_collect_discussion_truncates_long_discussion(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script_module("prepare_review_discussion", "prepare_review_discussion.py")

    issue_comments = [
        _comment(
            "alice", "x" * 500, f"2024-01-01T{i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z"
        )
        for i in range(0, 300)
    ]

    monkeypatch.setattr(
        module,
        "gh_api_list",
        lambda path: issue_comments if "issues" in path else [],
    )

    discussion = module.collect_discussion("owner/repo", "1", "DeepSeek")

    assert len(discussion) <= module.MAX_DISCUSSION_CHARS
    assert "truncated" in discussion


def test_gh_api_list_parses_paginated_json_arrays(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script_module(
        "prepare_review_discussion_paginate", "prepare_review_discussion.py"
    )

    class FakeResult:
        stdout = '[{"id": 1}]\n[{"id": 2}]'

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: FakeResult(),
    )

    assert module.gh_api_list("repos/owner/repo/issues/1/comments") == [{"id": 1}, {"id": 2}]
