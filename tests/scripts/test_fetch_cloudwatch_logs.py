"""Regression tests for scripts/bash/fetch-cloudwatch-logs.sh.

Exercises the script end-to-end with a stub `aws` binary on PATH so no live
AWS network calls are made (per CLAUDE.md).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bash" / "fetch-cloudwatch-logs.sh"

# On Windows, a bare "bash" on PATH may resolve to the WSL launcher
# (C:\Windows\System32\bash.exe), which cannot resolve native Windows paths.
# Pin to Git Bash explicitly so these tests are stable across environments.
_GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
BASH_EXE = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"


def _make_stub_aws(tmp_path: Path, stdout: str, exit_code: int) -> Path:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "aws"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s' {os.fsdecode(_shell_quote(stdout))}\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub_dir


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _run_script(*args: str, stub_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        [BASH_EXE, SCRIPT_PATH.as_posix(), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_rejects_non_numeric_lookback_seconds(tmp_path: Path) -> None:
    stub_dir = _make_stub_aws(tmp_path, stdout="None\n", exit_code=0)

    result = _run_script("my-log-group", "not-a-number", stub_dir=stub_dir)

    assert result.returncode == 0, "diagnostic log fetch must not fail the calling step"
    assert "::warning::lookback-seconds must be a non-negative integer" in result.stderr
    assert "not-a-number" in result.stderr


def test_rejects_negative_lookback_seconds(tmp_path: Path) -> None:
    stub_dir = _make_stub_aws(tmp_path, stdout="None\n", exit_code=0)

    result = _run_script("my-log-group", "-5", stub_dir=stub_dir)

    assert result.returncode == 0
    assert "::warning::lookback-seconds must be a non-negative integer" in result.stderr


def test_filters_none_and_prints_log_events(tmp_path: Path) -> None:
    stub_dir = _make_stub_aws(tmp_path, stdout="None\nlog line one\n", exit_code=0)

    result = _run_script("my-log-group", "600", stub_dir=stub_dir)

    assert result.returncode == 0
    assert "log line one" in result.stdout
    assert "None" not in result.stdout.splitlines()


def test_no_log_events_prints_placeholder(tmp_path: Path) -> None:
    stub_dir = _make_stub_aws(tmp_path, stdout="None\n", exit_code=0)

    result = _run_script("my-log-group", "600", stub_dir=stub_dir)

    assert result.returncode == 0
    assert "(no log events found)" in result.stdout


def test_aws_cli_failure_still_exits_zero_under_set_dash_e(tmp_path: Path) -> None:
    # A failing `aws` call must not abort the script via `set -e` before the
    # exit_code handling below it runs; this diagnostic step always exits 0.
    stub_dir = _make_stub_aws(
        tmp_path, stdout="AccessDeniedException: not authorized", exit_code=254
    )

    result = _run_script("my-log-group", "600", stub_dir=stub_dir)

    assert result.returncode == 0
    assert "::warning::logs:FilterLogEvents denied for my-log-group" in result.stdout
