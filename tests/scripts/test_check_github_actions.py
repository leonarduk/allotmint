"""Tests for the GitHub Actions status checker."""

import subprocess

import pytest

from scripts.developer_tools import n_check_github_actions


def test_filter_to_sha_keeps_matching_runs_only() -> None:
    runs = [
        {"databaseId": 1, "headSha": "abc123"},
        {"databaseId": 2, "headSha": "def456"},
    ]

    filtered = n_check_github_actions.filter_to_sha(runs, "abc123")

    assert filtered == [{"databaseId": 1, "headSha": "abc123"}]


def test_format_runs_prefers_conclusion_over_status() -> None:
    runs = [
        {
            "databaseId": 42,
            "name": "CI",
            "status": "completed",
            "conclusion": "failure",
            "url": "https://example.com/runs/42",
        },
        {
            "databaseId": 43,
            "name": "Backend Integration Tests",
            "status": "in_progress",
            "conclusion": None,
            "url": "https://example.com/runs/43",
        },
    ]

    output = n_check_github_actions.format_runs(runs)

    assert "[42] CI: failure  https://example.com/runs/42" in output
    assert "[43] Backend Integration Tests: in_progress  https://example.com/runs/43" in output


def test_run_gh_raises_systemexit_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["gh"], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(n_check_github_actions.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="boom"):
        n_check_github_actions.run_gh(["run", "list"])


def test_pr_head_sha_returns_none_when_no_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["gh"], returncode=1, stdout="", stderr="no PR found")

    monkeypatch.setattr(n_check_github_actions.subprocess, "run", fake_run)

    assert n_check_github_actions.pr_head_sha("some-branch") is None


def test_prompt_for_action_skips_when_not_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(n_check_github_actions.sys.stdin, "isatty", lambda: False)

    assert n_check_github_actions.prompt_for_action([{"databaseId": 1}]) == 0


def test_prompt_for_action_watches_entered_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(n_check_github_actions.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "99")
    watched: list[str] = []
    monkeypatch.setattr(
        n_check_github_actions, "watch_run", lambda run_id: watched.append(run_id) or 0
    )

    assert n_check_github_actions.prompt_for_action([{"databaseId": 99}]) == 0
    assert watched == ["99"]


def test_prompt_for_action_views_failed_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(n_check_github_actions.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "f99")
    viewed: list[str] = []
    monkeypatch.setattr(
        n_check_github_actions, "view_failed_log", lambda run_id: viewed.append(run_id)
    )

    assert n_check_github_actions.prompt_for_action([{"databaseId": 99}]) == 0
    assert viewed == ["99"]
