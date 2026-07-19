"""Tests for the pre-commit hook in scripts/build_tools/check_new_log_sanitisation.py
(issue #5262)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.build_tools import check_new_log_sanitisation as hook


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-b", "main"], repo)
    _run_git(["config", "user.email", "test@example.com"], repo)
    _run_git(["config", "user.name", "Test"], repo)
    return repo


def test_added_line_numbers_only_counts_plus_lines(git_repo: Path):
    target = git_repo / "example.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    _run_git(["add", "example.py"], git_repo)
    _run_git(["commit", "-m", "initial"], git_repo)

    # Replace line2 with two new lines, leaving line1/line3 untouched.
    target.write_text("line1\nnew_a\nnew_b\nline3\n", encoding="utf-8")
    _run_git(["add", "example.py"], git_repo)

    added = hook._added_line_numbers("example.py", cwd=git_repo)

    assert added == {2, 3}


def test_added_line_numbers_for_pure_append(git_repo: Path):
    target = git_repo / "example.py"
    target.write_text("line1\nline2\n", encoding="utf-8")
    _run_git(["add", "example.py"], git_repo)
    _run_git(["commit", "-m", "initial"], git_repo)

    target.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    _run_git(["add", "example.py"], git_repo)

    added = hook._added_line_numbers("example.py", cwd=git_repo)

    assert added == {3, 4}


def test_added_line_numbers_empty_for_unstaged_file(git_repo: Path):
    target = git_repo / "example.py"
    target.write_text("line1\n", encoding="utf-8")
    _run_git(["add", "example.py"], git_repo)
    _run_git(["commit", "-m", "initial"], git_repo)

    added = hook._added_line_numbers("example.py", cwd=git_repo)

    assert added == set()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/alerts.py", True),
        ("backend/routes/config.py", True),
        ("backend/logging_setup.py", False),
        ("backend/tests/test_alerts.py", False),
        ("tests/test_alerts.py", False),
        ("frontend/src/main.tsx", False),
        ("backend/README.md", False),
    ],
)
def test_is_backend_python_file(path: str, expected: bool):
    assert hook._is_backend_python_file(path) is expected


def test_main_flags_new_unwrapped_call_but_not_grandfathered_ones(monkeypatch):
    """A file with two unwrapped calls (one newly added, one pre-existing/
    grandfathered) must only be flagged for the new one."""
    monkeypatch.setattr(
        hook,
        "find_unwrapped_log_calls",
        lambda: [("backend/alerts.py", 10), ("backend/alerts.py", 50)],
    )
    monkeypatch.setattr(
        hook, "_added_line_numbers", lambda path, cwd=hook.REPO_ROOT: {50} if path == "backend/alerts.py" else set()
    )

    exit_code = hook.main(["backend/alerts.py"])

    assert exit_code == 1


def test_main_passes_when_no_new_lines_are_unwrapped(monkeypatch):
    monkeypatch.setattr(hook, "find_unwrapped_log_calls", lambda: [("backend/alerts.py", 10)])
    monkeypatch.setattr(hook, "_added_line_numbers", lambda path, cwd=hook.REPO_ROOT: {99})

    exit_code = hook.main(["backend/alerts.py"])

    assert exit_code == 0


def test_main_ignores_non_backend_files(monkeypatch):
    calls = []
    monkeypatch.setattr(hook, "find_unwrapped_log_calls", lambda: [])
    monkeypatch.setattr(
        hook,
        "_added_line_numbers",
        lambda path, cwd=hook.REPO_ROOT: calls.append(path) or set(),
    )

    exit_code = hook.main(["frontend/src/main.tsx", "backend/tests/test_alerts.py", "README.md"])

    assert exit_code == 0
    assert calls == []
