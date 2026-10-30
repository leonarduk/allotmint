# Shared helpers for the local dev scripts (run-backend.ps1,
# run-mcp-server.ps1); the PowerShell counterparts of scripts/bash/lib/.
# Dot-source it: . (Join-Path $PSScriptRoot 'lib\local-dev.ps1')

# Sets the variables from the repo's .env, else the shared env file outside
# every repo/worktree so credentials never need copying around (see
# ALLOTMINT_ENV_FILE in docs/CONTRIBUTOR_RUNBOOK.md). A repo-local .env wins.
# Child processes (e.g. the MCP server started by run-backend.ps1) inherit
# these. As with bash's `source` in load_env.sh, an `export ` prefix is
# allowed and one pair of surrounding quotes is stripped, so `KEY="value"` and
# `export KEY=value` mean the same under both scripts. This is not a full
# shell parser: escapes are not interpreted and an inline `# comment` after an
# unquoted value is kept as part of the value, so keep comments on their own
# lines.
function Import-AllotmintEnv([string]$RepoRoot) {
  $sharedEnvFile = if ($env:ALLOTMINT_ENV_FILE) { $env:ALLOTMINT_ENV_FILE } else { Join-Path $env:USERPROFILE 'workspace\GitHub\allotmint\.env.shared' }
  $repoEnvFile = Join-Path $RepoRoot '.env'
  $envFile = if (Test-Path $repoEnvFile) { $repoEnvFile } elseif (Test-Path $sharedEnvFile) { $sharedEnvFile } else { $null }
  if (-not $envFile) { return }
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*(?:export\s+)?([^#=\s]+)\s*=\s*(.*?)\s*$') {
      $name = $matches[1]
      $value = $matches[2]
      if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") { $value = $matches[1] }
      Set-Item -Path "Env:$name" -Value $value
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

# The allotmint-pro checkout the backend itself should import (the one the MCP
# server uses), so pro-only backend features work locally (e.g. the strategy
# stress test's long-history proxies, #9879); $null when $env:BACKEND_USE_PRO
# is '0' or there is no checkout.
function Get-BackendProDir([string]$RepoRoot) {
  if ($env:BACKEND_USE_PRO -eq '0') { return $null }
  return Get-AllotmintProDir $RepoRoot
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

# What must be stopped to free a port, given its listening PIDs and a snapshot
# of the running processes (ProcessId, ParentProcessId, CommandLine). Returns
# Pids, parents first so a uvicorn reloader cannot respawn a worker, and
# Foreign, the listeners whose command line does not match $Marker and which
# must be left alone. A listener is stopped along with the unbroken chain of
# ancestors that also match (venv launcher, reloader, npm, the run-*.ps1 shell)
# and all their descendants, so an unrelated shell above them is never touched.
# Windows can report a dead PID as the owner of a socket a child inherited; the
# children are judged in its place.
function Get-PortStopPlan([int[]]$Listeners, [object[]]$Processes, [string]$Marker) {
  $byId = @{}
  foreach ($process in $Processes) { $byId[[int]$process.ProcessId] = $process }
  $pids = [System.Collections.Generic.List[int]]::new()
  $foreign = [System.Collections.Generic.List[object]]::new()

  foreach ($id in $Listeners) {
    $owners = if ($byId.ContainsKey($id)) { @($byId[$id]) } else { @($Processes | Where-Object { [int]$_.ParentProcessId -eq $id }) }
    if ($owners.Count -eq 0) { $foreign.Add([pscustomobject]@{ ProcessId = $id; CommandLine = '' }) }
    foreach ($owner in $owners) {
      if ($owner.CommandLine -notmatch $Marker) { $foreign.Add($owner); continue }

      $top = $owner
      $seen = @{ ([int]$top.ProcessId) = $true }
      while ($true) {
        $parentId = [int]$top.ParentProcessId
        if ($seen.ContainsKey($parentId) -or -not $byId.ContainsKey($parentId)) { break }
        if ($byId[$parentId].CommandLine -notmatch $Marker) { break }
        $top = $byId[$parentId]
        $seen[$parentId] = $true
      }

      $queue = [System.Collections.Generic.Queue[object]]::new()
      $queue.Enqueue($top)
      while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        if ($pids.Contains([int]$current.ProcessId)) { continue }
        $pids.Add([int]$current.ProcessId)
        foreach ($child in @($Processes | Where-Object { [int]$_.ParentProcessId -eq [int]$current.ProcessId })) { $queue.Enqueue($child) }
      }
    }
  }
  return [pscustomobject]@{ Pids = @($pids); Foreign = @($foreign) }
}
