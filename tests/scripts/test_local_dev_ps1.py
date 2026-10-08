"""Tests for Import-AllotmintEnv in scripts/lib/local-dev.ps1 (run-backend.ps1, run-mcp-server.ps1).

The MCP server started by run-backend.ps1 inherits the variables this loads, so
e.g. ALLOTMINT_MCP_BRAVE_API_KEY in the shared env file reaches ``search_web``
(#9198). Skipped where no launchable PowerShell is available (``pwsh`` missing,
or an AppX/Store install that a non-interactive subprocess cannot spawn).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "local-dev.ps1"


def _resolve_pwsh() -> str | None:
    """Return a launchable PowerShell, or None.

    ``shutil.which("pwsh")`` can resolve to the Microsoft Store / AppX shim
    under ``WindowsApps``, which ``CreateProcess`` refuses to launch from a
    non-interactive context (``PermissionError: [WinError 5]``). Probe the
    candidate before handing it to the tests so an unlaunchable shim degrades
    to a skip rather than a hard failure.
    """
    for name in ("pwsh", "powershell"):
        candidate = shutil.which(name)
        if not candidate:
            continue
        try:
            subprocess.run(
                [candidate, "-NoProfile", "-NonInteractive", "-Command", "exit 0"],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return candidate
    return None


PWSH = _resolve_pwsh()

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not installed or not launchable")


def _find_shell() -> str | None:
    """Return a launchable PowerShell executable, or None.

    Prefers ``pwsh`` (PowerShell 7) but skips AppX/Store installs under
    ``WindowsApps``: Windows blocks ``CreateProcess`` on those from a
    non-interactive context (``WinError 5``), which would fail the whole file
    on sandboxed CI hosts. Falls back to Windows PowerShell 5.1, which is
    always present and launchable on Windows.
    """
    for name in ("pwsh", "powershell"):
        exe = shutil.which(name)
        if not exe or "WindowsApps" in exe:
            continue
        try:
            subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", "exit 0"],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return exe
    return None


PWSH = _find_shell()

pytestmark = pytest.mark.skipif(PWSH is None, reason="no launchable PowerShell available")


def _run_powershell(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run ``script`` under the resolved shell, skipping if it cannot be spawned."""
    try:
        return subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            env=env,
            check=True,
            timeout=60,
        )
    except PermissionError as exc:  # pragma: no cover - sandbox restriction
        pytest.skip(f"PowerShell cannot be spawned in this environment: {exc}")
    except OSError as exc:  # pragma: no cover - sandbox restriction
        pytest.skip(f"PowerShell cannot be spawned in this environment: {exc}")


def _child_sees(tmp_path: Path, env_lines: str, name: str) -> str:
    """Import the env file, then print ``name`` as seen by a child process."""
    shared = tmp_path / "shared.env"
    shared.write_text(env_lines, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    script = (
        f". '{LIB}'; Import-AllotmintEnv '{repo}'; "
        f"& '{PWSH}' -NoProfile -Command '[Environment]::GetEnvironmentVariable(\"{name}\")'"
    )
    env = {**os.environ, "ALLOTMINT_ENV_FILE": str(shared)}
    env.pop(name, None)
    result = _run_powershell(script, env=env)
    return result.stdout.strip()


def test_shared_env_variable_reaches_child_processes(tmp_path):
    assert _child_sees(tmp_path, "ALLOTMINT_MCP_BRAVE_API_KEY=test-key\n", "ALLOTMINT_MCP_BRAVE_API_KEY") == "test-key"


@pytest.mark.parametrize(
    "line",
    ['KEY_9198="test-key"', "KEY_9198='test-key'", "KEY_9198 = test-key  ", "export KEY_9198=test-key"],
)
def test_quotes_padding_and_export_are_handled_like_bash_source(tmp_path, line):
    assert _child_sees(tmp_path, f"# comment\n{line}\n", "KEY_9198") == "test-key"


def _backend_pro_dir(tmp_path: Path, use_pro: str | None, with_checkout: bool = True) -> str:
    """``Get-BackendProDir`` for a repo whose sibling allotmint-pro has (or lacks) an MCP package (#9879)."""
    repo = tmp_path / "allotmint"
    repo.mkdir()
    if with_checkout:
        (tmp_path / "allotmint-pro" / "allotmint_pro" / "mcp_server").mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ("ALLOTMINT_PRO_DIR", "BACKEND_USE_PRO")}
    if use_pro is not None:
        env["BACKEND_USE_PRO"] = use_pro
    result = _run_powershell(f". '{LIB}'; Get-BackendProDir '{repo}'", env=env)
    return result.stdout.strip()


def test_backend_imports_the_sibling_pro_checkout(tmp_path):
    assert Path(_backend_pro_dir(tmp_path, None)) == tmp_path / "allotmint-pro"


def test_backend_use_pro_0_runs_the_backend_free_only(tmp_path):
    assert _backend_pro_dir(tmp_path, "0") == ""


def test_no_pro_checkout_means_no_pro_for_the_backend(tmp_path):
    assert _backend_pro_dir(tmp_path, None, with_checkout=False) == ""


def test_backend_pythonpath_keeps_an_existing_pythonpath():
    """run-backend.ps1 sets the backend's PYTHONPATH with Get-McpServerPythonPath: repo, pro, then the old value."""
    # Plain names: a drive letter's colon is the path separator on Linux runners.
    env = {**os.environ, "PYTHONPATH": "existing"}
    result = _run_powershell(f". '{LIB}'; Get-McpServerPythonPath 'repo' 'pro'", env=env)
    assert result.stdout.strip().split(os.pathsep) == ["repo", "pro", "existing"]
