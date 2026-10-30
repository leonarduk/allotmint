# Restart the local stack: stop whatever is running on the MCP server, backend
# and frontend ports, then start run-mcp-server.ps1, run-backend.ps1 and
# run-frontend.ps1 from this checkout, each in its own window. Ctrl+C in a
# window stops that service; running this again replaces all three.
#
# Usage: .\scripts\run-all.ps1
#   Ports: server.uvicorn_port in config.yaml (backend), 2568 (frontend),
#   MCP_SERVER_URL / MCP_SERVER_PORT, else 8001 (MCP server). The MCP server is
#   skipped under the same conditions as run-backend.ps1. Only these services
#   are stopped: if anything else holds a port, nothing is stopped or started.
#   Windows only; on macOS/Linux start the scripts/bash/ launchers yourself.
$ErrorActionPreference = 'Stop'

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT
. (Join-Path $SCRIPT_DIR 'lib\local-dev.ps1')

Import-AllotmintEnv $REPO_ROOT

function Get-BackendPort {
  $match = Select-String -Path (Join-Path $REPO_ROOT 'config.yaml') -Pattern '^\s+uvicorn_port:\s*(\d+)' | Select-Object -First 1
  if ($match) { return [int]$match.Matches[0].Groups[1].Value }
  return 6468
}

# Mirrors Start-LocalMcpServer in run-backend.ps1. $null means no local server.
function Get-McpPort {
  if ($env:START_MCP_SERVER -eq '0') { return $null }
  if (-not (Get-AllotmintProDir $REPO_ROOT)) {
    Write-Host "allotmint-pro not found at $(Get-AllotmintProCandidate $REPO_ROOT); skipping the MCP server." -ForegroundColor Yellow
    return $null
  }
  $port = if ($env:MCP_SERVER_PORT) { $env:MCP_SERVER_PORT } else { '8001' }
  if ($env:MCP_SERVER_URL) {
    if ($env:MCP_SERVER_URL -notmatch '^http://(localhost|127\.0\.0\.1)(:(\d+))?(/|$)') { return $null }
    $port = if ($matches[3]) { $matches[3] } else { '80' }
  }
  if (-not (Test-ValidPort $port)) { throw "Invalid MCP server port '$port' (from MCP_SERVER_PORT or MCP_SERVER_URL; expected 1-65535)." }
  return [int]$port
}

# A listening socket is the one with no remote end. Not -State Listen: some
# Windows machines report scrambled TCP states (netstat showing 0.0.0.0:135 as
# FIN_WAIT_1), and that filter then misses real listeners.
function Get-Listeners([int]$Port) {
  return @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.RemotePort -eq 0 } |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

# Processes of $Service that hold no socket yet or no longer do: a launcher from
# this checkout still installing, or left open after a crash, and a server still
# in startup (the MCP server binds its port only once that finishes).
function Get-UnboundProcesses([object]$Service, [object[]]$Processes) {
  $scriptPath = [regex]::Escape((Join-Path $SCRIPT_DIR $Service.Script))
  $pattern = "$scriptPath|(?:$($Service.Marker)).*--port\s+$($Service.Port)\b"
  return @($Processes | Where-Object { $_.CommandLine -match $pattern } | ForEach-Object { [int]$_.ProcessId })
}

function Wait-ForPort([int]$Port, [bool]$Listening, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (((Get-Listeners $Port).Count -gt 0) -eq $Listening) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return ((Get-Listeners $Port).Count -gt 0) -eq $Listening
}

# Started in this order and one at a time: the backend leaves the MCP port alone
# only if the server is already listening, and the frontend reads the port the
# backend records. Timeouts allow for the installs in run-backend / run-frontend.
$services = @()
$mcpPort = Get-McpPort
if ($mcpPort) {
  $services += [pscustomobject]@{
    Name = 'MCP server'; Port = $mcpPort; Url = "http://localhost:$mcpPort/mcp"
    Script = 'run-mcp-server.ps1'; Arguments = @('-Port', $mcpPort); TimeoutSeconds = 300
    Marker = 'allotmint_pro\.mcp_server\.app:app|run-mcp-server\.(ps1|sh)|--multiprocessing-fork'
  }
}
$backendPort = Get-BackendPort
$services += [pscustomobject]@{
  Name = 'Backend'; Port = $backendPort; Url = "http://localhost:$backendPort"
  Script = 'run-backend.ps1'; Arguments = @(); TimeoutSeconds = 600
  Marker = 'backend\.local_api\.main:app|run-backend\.ps1|run-local-api\.sh|--multiprocessing-fork'
}
$services += [pscustomobject]@{
  Name = 'Frontend'; Port = 2568; Url = 'http://localhost:2568'
  Script = 'run-frontend.ps1'; Arguments = @(); TimeoutSeconds = 300
  Marker = '\bvite\b|\brun dev\b|run-frontend\.(ps1|sh)'
}

# Check every port before stopping anything, so a foreign process cannot leave
# the stack half stopped.
$processes = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, CommandLine)
$toStop = @()
$blocked = $false
foreach ($service in $services) {
  $found = @(Get-Listeners $service.Port) + @(Get-UnboundProcesses $service $processes)
  $plan = Get-PortStopPlan -Listeners $found -Processes $processes -Marker $service.Marker
  foreach ($process in $plan.Foreign) {
    Write-Host "Port $($service.Port) ($($service.Name)) is held by something else, pid $($process.ProcessId): $($process.CommandLine)" -ForegroundColor Red
    $blocked = $true
  }
  $toStop += @($plan.Pids | Where-Object { $_ -ne $PID })
}
if ($blocked) {
  Write-Host 'Nothing was stopped or started. Stop that process and run this again.' -ForegroundColor Red
  exit 1
}

foreach ($id in ($toStop | Select-Object -Unique)) {
  Write-Host "Stopping pid $id" -ForegroundColor Yellow
  # A child can exit with its parent before its turn; the port check below is
  # what decides whether the stop worked.
  Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
foreach ($service in $services) {
  if (-not (Wait-ForPort $service.Port $false 15)) {
    Write-Host "Port $($service.Port) ($($service.Name)) is still in use after stopping its processes." -ForegroundColor Red
    exit 1
  }
}

$shell = (Get-Command pwsh, powershell -ErrorAction SilentlyContinue | Select-Object -First 1).Source
$failed = $false
foreach ($service in $services) {
  Write-Host "Starting $($service.Name) on port $($service.Port)..." -ForegroundColor Cyan
  $scriptPath = Join-Path $SCRIPT_DIR $service.Script
  # -NoExit keeps the window open with the error if the service fails to start.
  $arguments = @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$scriptPath`"") + $service.Arguments
  Start-Process -FilePath $shell -ArgumentList $arguments -WorkingDirectory $REPO_ROOT | Out-Null
  if (-not (Wait-ForPort $service.Port $true $service.TimeoutSeconds)) {
    Write-Host "$($service.Name) did not start listening on port $($service.Port) within $($service.TimeoutSeconds)s; see its window." -ForegroundColor Red
    $failed = $true
    continue
  }
  Write-Host "$($service.Name) is up at $($service.Url)" -ForegroundColor Green
}
if ($failed) { exit 1 }
