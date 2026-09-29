# Shared helpers for the local dev scripts (run-backend.ps1,
# run-mcp-server.ps1); the PowerShell counterparts of scripts/bash/lib/.
# Dot-source it: . (Join-Path $PSScriptRoot 'lib\local-dev.ps1')

# Sets the variables from the repo's .env, else the shared env file outside
# every repo/worktree so credentials never need copying around (see
# ALLOTMINT_ENV_FILE in docs/CONTRIBUTOR_RUNBOOK.md). A repo-local .env wins.
function Import-AllotmintEnv([string]$RepoRoot) {
  $sharedEnvFile = if ($env:ALLOTMINT_ENV_FILE) { $env:ALLOTMINT_ENV_FILE } else { Join-Path $env:USERPROFILE 'workspace\GitHub\allotmint\.env.shared' }
  $repoEnvFile = Join-Path $RepoRoot '.env'
  $envFile = if (Test-Path $repoEnvFile) { $repoEnvFile } elseif (Test-Path $sharedEnvFile) { $sharedEnvFile } else { $null }
  if (-not $envFile) { return }
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)\s*$') {
      Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
  }
}

# Where the allotmint-pro checkout is looked for: $env:ALLOTMINT_PRO_DIR, else
# the sibling ..\allotmint-pro.
function Get-AllotmintProCandidate([string]$RepoRoot) {
  if ($env:ALLOTMINT_PRO_DIR) { return $env:ALLOTMINT_PRO_DIR }
  return Join-Path (Split-Path -Parent $RepoRoot) 'allotmint-pro'
}

# The allotmint-pro checkout, or $null if it has no MCP server package.
function Get-AllotmintProDir([string]$RepoRoot) {
  $proDir = Get-AllotmintProCandidate $RepoRoot
  if (Test-Path (Join-Path $proDir 'allotmint_pro\mcp_server')) { return $proDir }
  return $null
}

# True if $Value is a TCP port number (1-65535).
function Test-ValidPort([string]$Value) {
  $number = 0
  return ($Value -match '^\d+$') -and [int]::TryParse($Value, [ref]$number) -and $number -ge 1 -and $number -le 65535
}

# PYTHONPATH for the MCP server: it imports `backend` from the repo root and
# `allotmint_pro` from the checkout.
function Get-McpServerPythonPath([string]$RepoRoot, [string]$ProDir) {
  return (@($RepoRoot, $ProDir, $env:PYTHONPATH) | Where-Object { $_ }) -join [System.IO.Path]::PathSeparator
}

# `python` arguments that run the MCP server on 127.0.0.1:$Port.
function Get-McpServerArguments([int]$Port) {
  return @('-m', 'uvicorn', 'allotmint_pro.mcp_server.app:app', '--host', '127.0.0.1', '--port', $Port)
}

# True if nothing is listening on 127.0.0.1:$Port.
function Test-PortFree([int]$Port) {
  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
  try {
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    $listener.Stop()
  }
}
