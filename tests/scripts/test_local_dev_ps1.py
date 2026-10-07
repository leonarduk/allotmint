"""Tests for Import-AllotmintEnv in scripts/lib/local-dev.ps1 (run-backend.ps1, run-mcp-server.ps1).

The MCP server started by run-backend.ps1 inherits the variables this loads, so
e.g. ALLOTMINT_MCP_BRAVE_API_KEY in the shared env file reaches ``search_web``
(#9198). Skipped where PowerShell 7 (``pwsh``) is not installed.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "local-dev.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not installed")


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
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=60,
    )
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
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", f". '{LIB}'; Get-BackendProDir '{repo}'"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


def test_backend_imports_the_sibling_pro_checkout(tmp_path):
    assert Path(_backend_pro_dir(tmp_path, None)) == tmp_path / "allotmint-pro"


def test_backend_use_pro_0_runs_the_backend_free_only(tmp_path):
    assert _backend_pro_dir(tmp_path, "0") == ""


def test_no_pro_checkout_means_no_pro_for_the_backend(tmp_path):
    assert _backend_pro_dir(tmp_path, None, with_checkout=False) == ""


def test_backend_pythonpath_keeps_an_existing_pythonpath():
    """run-backend.ps1 sets the backend's PYTHONPATH with Get-McpServerPythonPath: repo, pro, then the old value."""
    env = {**os.environ, "PYTHONPATH": "C:\\existing"}
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", f". '{LIB}'; Get-McpServerPythonPath 'C:\\repo' 'C:\\pro'"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=60,
    )
    assert result.stdout.strip().split(os.pathsep) == ["C:\\repo", "C:\\pro", "C:\\existing"]
