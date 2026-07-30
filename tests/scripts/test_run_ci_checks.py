"""Tests for the local GitHub Actions check runner."""

import subprocess
from pathlib import Path

import pytest

from scripts.developer_tools import g_run_ci_checks


def test_select_checks_preserves_catalog_order() -> None:
    args = g_run_ci_checks.parse_args(["--check", "scripts", "--check", "backend"])

    selected = g_run_ci_checks.select_checks(args)

    assert [check.name for check in selected] == ["backend", "scripts"]


def test_noninteractive_invocation_requires_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    args = g_run_ci_checks.parse_args([])
    monkeypatch.setattr(g_run_ci_checks.sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit, match="No check selected"):
        g_run_ci_checks.select_checks(args)


def test_dry_run_does_not_start_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run started a process")

    monkeypatch.setattr(g_run_ci_checks.subprocess, "run", unexpected_run)

    assert g_run_ci_checks.run_checks([g_run_ci_checks.CHECKS[0]], Path.cwd(), True, False) == 0


def test_keep_going_runs_remaining_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    return_codes = iter((2, 0))
    calls: list[str] = []

    def fake_run(command: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, next(return_codes))

    check = g_run_ci_checks.Check("sample", "Sample", "workflow.yml", ("first", "second"))
    monkeypatch.setattr(g_run_ci_checks.subprocess, "run", fake_run)

    assert g_run_ci_checks.run_checks([check], Path.cwd(), False, True) == 1
    assert calls == ["first", "second"]
