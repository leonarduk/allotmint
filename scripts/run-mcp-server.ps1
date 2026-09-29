# Start allotmint-pro's MCP server (the tools behind the chat drawer) in the
# foreground, for when you want it in its own terminal rather than started in
# the background by run-backend.ps1 (which then finds the port in use and
# leaves it alone). Ctrl+C stops it.
#
# Usage: .\scripts\run-mcp-server.ps1 [-Port 8001]
#   -Port defaults to $env:MCP_SERVER_PORT, else 8001. Needs an allotmint-pro
#   checkout at $env:ALLOTMINT_PRO_DIR, else the sibling ..\allotmint-pro.
#   Point the backend at it with MCP_SERVER_URL=http://localhost:<port>/mcp.
Param(
  [int]$Port = $(if ($env:MCP_SERVER_PORT) { [int]$env:MCP_SERVER_PORT } else { 8001 })
)

$ErrorActionPreference = 'Stop'

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT
. (Join-Path $SCRIPT_DIR 'lib\local-dev.ps1')

# The server imports `backend`, which reads the same env as the backend.
Import-AllotmintEnv $REPO_ROOT

$proDir = Get-AllotmintProDir $REPO_ROOT
if (-not $proDir) {
  Write-Host "allotmint-pro not found at $(Get-AllotmintProCandidate $REPO_ROOT); clone it there or set ALLOTMINT_PRO_DIR." -ForegroundColor Red
  exit 1
}

if (-not (Test-PortFree $Port)) {
  Write-Host "Port $Port is already in use (an MCP server may already be running); pass -Port or stop it first." -ForegroundColor Red
  exit 1
}

# Prefer the repo's virtualenv (created by run-backend.ps1), else python / py.
$venvPython = Join-Path $REPO_ROOT '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' }
          else { Write-Host 'Python not found; install it from https://www.python.org/downloads/' -ForegroundColor Red; exit 1 }

$env:PYTHONPATH = Get-McpServerPythonPath $REPO_ROOT $proDir
Write-Host "Starting the MCP server at http://localhost:$Port/mcp (allotmint-pro: $proDir)" -ForegroundColor Green
& $python @(Get-McpServerArguments $Port)
exit $LASTEXITCODE
