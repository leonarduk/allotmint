"""Pin that the local launchers hand the env file's credentials to the MCP server (#9198).

allotmint-pro's MCP server reads e.g. ``ALLOTMINT_MCP_BRAVE_API_KEY`` from its own
environment. Neither launcher passes it explicitly: the server inherits whatever
the env file loaded. That only works while (a) the env file is loaded *before*
the server is started and (b) the server is not spawned with a replacement
environment. The behaviour itself is exercised by tests/bash/start_mcp_server.bats,
tests/bash/load_env.bats and tests/scripts/test_local_dev_ps1.py; these static
checks guard the ordering in the top-level scripts, which those tests don't run.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_LOCAL_API = ROOT / "scripts" / "bash" / "run-local-api.sh"
START_MCP_LIB = ROOT / "scripts" / "bash" / "lib" / "start_mcp_server.sh"
RUN_BACKEND = ROOT / "scripts" / "run-backend.ps1"


def _first_line(text: str, pattern: str) -> int:
    """1-based number of the first line matching ``pattern`` (fails if absent)."""
    for number, line in enumerate(text.splitlines(), start=1):
        if re.search(pattern, line):
            return number
    raise AssertionError(f"no line matches {pattern!r}")


def test_run_local_api_loads_env_before_starting_mcp_server():
    text = RUN_LOCAL_API.read_text(encoding="utf-8")
    loaded = _first_line(text, r"^\s*load_allotmint_env\b")
    started = _first_line(text, r"^\s*start_local_mcp_server\b")
    assert loaded < started


def test_run_backend_ps1_loads_env_before_starting_mcp_server():
    text = RUN_BACKEND.read_text(encoding="utf-8")
    loaded = _first_line(text, r"^\s*Import-AllotmintEnv\b")
    started = _first_line(text, r"^\s*\$mcpProcess\s*=\s*Start-LocalMcpServer\b")
    assert loaded < started


def test_bash_mcp_server_is_not_started_with_a_replacement_environment():
    text = START_MCP_LIB.read_text(encoding="utf-8")
    assert not re.search(r"\benv\s+-i\b|\benv\s+--ignore-environment\b", text)


def test_ps1_mcp_server_is_not_started_with_a_replacement_environment():
    text = RUN_BACKEND.read_text(encoding="utf-8")
    start = _first_line(text, r"^function Start-LocalMcpServer\b")
    end = _first_line(text, r"^\$mcpProcess\s*=\s*Start-LocalMcpServer\b")
    body = "\n".join(text.splitlines()[start - 1 : end - 1])
    assert "Start-Process" in body
    # PowerShell 7.4+ `Start-Process -Environment` / -UseNewEnvironment would
    # replace the inherited variables the env file set.
    assert not re.search(r"-Environment\b|-UseNewEnvironment\b", body)
