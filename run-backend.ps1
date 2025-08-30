Param(
  [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

Write-Host "# -------- Configuration --------" -ForegroundColor DarkCyan
Write-Host "# Set offline_mode: true in config.yaml to skip dependency installation" -ForegroundColor DarkCyan
Write-Host "# --------------------------------" -ForegroundColor DarkCyan

# ───────────────── repo root ─────────────────
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

# ───────────────── helpers ───────────────────
function Get-HasCommand($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Coalesce([object]$value, [object]$fallback) {
  if ($null -ne $value -and $value -ne '') { return $value }
  return $fallback
}

function Read-YamlSimple([string]$path) {
  # Minimal key:value YAML parser (scalars only; ignores lists/nesting)
  $result = @{}
  if (-not (Test-Path $path)) { return [pscustomobject]$result }
  foreach ($line in Get-Content $path) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^\s*([A-Za-z0-9_]+)\s*:\s*(.*)\s*$') {
      $k = $matches[1]
      $v = $matches[2].Trim()
      if ($v -match '^["''](.*)["'']$') { $v = $matches[1] } # strip quotes
      switch -Regex ($v.ToLower()) {
        '^(true|yes)$'  { $v = $true;  break }
        '^(false|no)$'  { $v = $false; break }
        '^\d+$'         { $v = [int]$v; break }
        default { }
      }
      $result[$k] = $v
    }
  }
  return [pscustomobject]$result
}

function Read-Config([string]$path) {
  if (-not (Test-Path $path)) { return [pscustomobject]@{} }

  # Prefer native ConvertFrom-Yaml if available (PS7 or module), else fallback
  if (Get-HasCommand 'ConvertFrom-Yaml') {
    return (Get-Content $path -Raw | ConvertFrom-Yaml)
  }
  try {
    Import-Module powershell-yaml -ErrorAction Stop
    return (Get-Content $path -Raw | ConvertFrom-Yaml)
  } catch {
    Write-Host '⚠️  ConvertFrom-Yaml unavailable; using simple YAML parser (scalars only).' -ForegroundColor Yellow
    return Read-YamlSimple $path
  }
}

# ───────────── create & activate venv ─────────
if (-not (Test-Path '.\.venv\Scripts\Activate.ps1')) {
  Write-Host 'Creating Python virtual environment (.venv)...' -ForegroundColor Yellow
  python -m venv .venv
}

Write-Host 'Activating virtual environment...' -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

# ───────────────── load config ────────────────
$configPath = Join-Path $SCRIPT_DIR 'config.yaml'
$cfg = Read-Config $configPath

# ───────────── offline mode & installs ────────
$offline = $false
if ($cfg.PSObject.Properties.Name -contains 'offline_mode') {
  $offline = [bool]$cfg.offline_mode
}

if (-not $offline) {
  Write-Host 'Installing backend requirements...' -ForegroundColor Yellow
  python -m pip install -r .\requirements.txt
} else {
  Write-Host 'Offline mode detected; skipping dependency installation.' -ForegroundColor Yellow
}

# ───────────── env + defaults (PS 5.1) ────────
$env:ALLOTMINT_ENV = Coalesce $cfg.app_env 'local'
$host      = Coalesce $cfg.uvicorn_host '0.0.0.0'
$port      = Coalesce $cfg.uvicorn_port $Port
$logConfig = Coalesce $cfg.log_config   'logging.ini'
$reloadRaw = Coalesce $cfg.reload       $true
$reload    = [bool]$reloadRaw

# ───────────── start server ───────────────────
Write-Host "Starting AllotMint Local API on http://$host:$port ..." -ForegroundColor Green

$arguments = @(
  'backend.local_api.main:app',
  '--reload-dir', 'backend',
  '--port', $port,
  '--host', $host,
  '--log-config', $logConfig,
  '--app-dir', '.'
)
if ($reload) { $arguments += '--reload' }

python -m uvicorn @arguments
