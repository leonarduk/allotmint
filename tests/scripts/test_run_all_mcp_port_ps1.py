"""Tests for Get-McpPort in scripts/run-all.ps1 (#11137).

It decides which port run-all.ps1 frees and waits on for the MCP server, so
these pin the port it reads from MCP_SERVER_URL and the URLs it refuses.
run-all.ps1 stops and starts processes at top level, so it is never run: the
function's own text is taken from the parsed file and defined on its own.
Skipped where no launchable PowerShell is available.
"""

import json
import os
from pathlib import Path

import pytest

from tests.scripts.test_local_dev_ps1 import LIB, PWSH, _run_powershell

RUN_ALL = Path(__file__).resolve().parents[2] / "scripts" / "run-all.ps1"
REJECTED = "is not plain-HTTP localhost; skipping the MCP server."

pytestmark = pytest.mark.skipif(PWSH is None, reason="no launchable PowerShell available")

# Defines Get-McpPort from run-all.ps1 without running the script, calls it, and
# prints its result, the Write-Host messages (stream 6) and any thrown error.
_CALL_GET_MCP_PORT = """
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:TEST_RUN_ALL, [ref]$null, [ref]$null)
$definition = $ast.Find({
  param($node)
  $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-McpPort'
}, $true)
. ([scriptblock]::Create($definition.Extent.Text))
$port = $null
$messages = @()
$thrown = $null
try {
  foreach ($item in @(Get-McpPort 6>&1)) {
    if ($item -is [System.Management.Automation.InformationRecord]) { $messages += "$($item.MessageData)" }
    else { $port = $item }
  }
} catch { $thrown = $_.Exception.Message }
[pscustomobject]@{ port = $port; messages = $messages; thrown = $thrown } | ConvertTo-Json -Compress
"""


def _get_mcp_port(tmp_path: Path, url: str) -> dict:
    """``Get-McpPort`` with ``MCP_SERVER_URL=url`` and an allotmint-pro checkout present."""
    repo = tmp_path / "allotmint"
    repo.mkdir()
    pro = tmp_path / "allotmint-pro"
    (pro / "allotmint_pro" / "mcp_server").mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ("MCP_SERVER_PORT", "START_MCP_SERVER")}
    env.update(MCP_SERVER_URL=url, ALLOTMINT_PRO_DIR=str(pro), TEST_RUN_ALL=str(RUN_ALL))
    script = f". '{LIB}'; $REPO_ROOT = '{repo}'; {_CALL_GET_MCP_PORT}"
    return json.loads(_run_powershell(script, env=env).stdout)


@pytest.mark.parametrize(
    ("url", "port"),
    [
        ("http://localhost", 80),
        ("http://localhost:3000", 3000),
        ("http://127.0.0.1", 80),
        ("http://127.0.0.1:3000", 3000),
        # A trailing path is not part of the port.
        ("http://localhost:3000/mcp", 3000),
        ("http://127.0.0.1/mcp", 80),
        # Matched case-insensitively (the IgnoreCase option).
        ("http://LOCALHOST", 80),
        ("HTTP://LocalHost:3000/mcp", 3000),
    ],
)
def test_port_comes_from_a_plain_http_localhost_url(tmp_path, url, port):
    assert _get_mcp_port(tmp_path, url) == {"port": port, "messages": [], "thrown": None}


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost:3000",
        "ftp://127.0.0.1",
        "http://example.com:3000",
        "http://localhost.example.com",
        "localhost:3000",
        "http://localhost:abc",
    ],
)
def test_other_urls_skip_the_server_with_a_message(tmp_path, url):
    result = _get_mcp_port(tmp_path, url)

    assert result["port"] is None
    assert result["thrown"] is None
    assert result["messages"] == [f"MCP_SERVER_URL ({url}) {REJECTED}"]


def test_an_out_of_range_url_port_is_an_error(tmp_path):
    result = _get_mcp_port(tmp_path, "http://localhost:70000")

    assert result["port"] is None
    assert result["thrown"].startswith("Invalid MCP server port '70000'")
