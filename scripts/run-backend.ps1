Param(
  [int]$Port = 8000,
  [switch]$Offline
)

$ErrorActionPreference = 'Stop'

# Ensure Python is available (try `python` then `py`)
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

function Get-ConfigValue([object]$obj, [object[]]$path, [object]$default) {
  try {
    $cur = $obj
    foreach ($key in $path) {
      if ($null -eq $cur) { return $default }
      if ($cur -is [hashtable]) {
        if (-not $cur.ContainsKey($key)) { return $default }
        $cur = $cur[$key]
      } elseif ($cur.PSObject -and ($cur.PSObject.Properties.Name -contains $key)) {
        $cur = $cur.$key
      } else {
        return $default
      }
    }
    if ($null -eq $cur -or $cur -eq '') { return $default }
    return $cur
  } catch {
    return $default
  }
}

# ───────────────── helpers ───────────────────
function Get-HasCommand($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Coalesce([object]$value, [object]$fallback) {
  if ($null -ne $value -and $value -ne '') { return $value }
  return $fallback
}

function Read-YamlSimple([string]$path) {
  # Minimal YAML parser supporting nested hashtables via indentation (scalars only; ignores lists)
  $result = @{}
  if (-not (Test-Path $path)) { return [pscustomobject]$result }

  $stack = New-Object System.Collections.ArrayList
  $null = $stack.Add([pscustomobject]@{Indent=-1; Node=$result})

  foreach ($line in Get-Content $path) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^(\s*)([A-Za-z0-9_]+)\s*:\s*(.*)$') {
      $indent = $matches[1].Length
      $k = $matches[2]
      $v = $matches[3].Trim()

      while ($stack[$stack.Count-1].Indent -ge $indent) {
        $stack.RemoveAt($stack.Count-1)
      }
      $parent = $stack[$stack.Count-1].Node

      if ($v -eq '') {
        $child = @{}
        $parent[$k] = $child
        $null = $stack.Add([pscustomobject]@{Indent=$indent; Node=$child})
        continue
      }

      if ($v -notmatch '^["''].*["'']$') { $v = $v -replace '\s+#.*$', '' }
      if ($v -match '^["''](.*)["'']$') { $v = $matches[1] } # strip quotes
      switch -Regex ($v.ToLower()) {
        '^(true|yes)$'  { $v = $true;  break }
        '^(false|no)$'  { $v = $false; break }
        '^\d+$'         { $v = [int]$v; break }
        default { }
      }
      $parent[$k] = $v
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
if (-not $pythonCmd) {
  Write-Host 'Python is required but was not found. Install it from https://www.python.org/downloads/' -ForegroundColor Red
  exit 1
}
$PYTHON = $pythonCmd.Name

Write-Host "# -------- Configuration --------" -ForegroundColor DarkCyan
Write-Host "# Set market_data.offline_mode: true in config.yaml to skip dependency installation" -ForegroundColor DarkCyan
Write-Host "# You can also pass -Offline to this script" -ForegroundColor DarkCyan
Write-Host "# --------------------------------" -ForegroundColor DarkCyan

# ───────────────── repo root ─────────────────
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT

# Load environment variables from .env if present
if (Test-Path '.env') {
    Get-Content '.env' | ForEach-Object {
        if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)\s*$') {
            $key = $matches[1]; $value = $matches[2];
            Set-Item -Path Env:$key -Value $value
        }
    }
}

# ───────────────── load config ────────────────
$configPath = Join-Path $REPO_ROOT 'config.yaml'
$cfg = Read-Config $configPath

# ───────────── offline mode & installs ────────
$offline = $false
if ($cfg.PSObject.Properties.Name -contains 'offline_mode') {
  $offline = [bool]$cfg.offline_mode
}

# Derive offline mode (param overrides config)
$offlineCfg = Get-ConfigValue $cfg @('market_data','offline_mode') $false
$offline = ($Offline.IsPresent -and $Offline) -or [bool]$offlineCfg

# Ensure data directory exists
if (-not (Test-Path 'data') -or -not (Get-ChildItem 'data' -ErrorAction SilentlyContinue)) {
  if (-not $offline) {
    Write-Host 'Data directory missing; syncing...' -ForegroundColor Yellow
    bash scripts/sync_data.sh
  } else {
    Write-Host 'Data directory missing; offline mode prevents automatic sync.' -ForegroundColor Yellow
  }
}

# Place synthesized CDK templates outside the repository
$env:CDK_OUTDIR = Join-Path $SCRIPT_DIR '..\.cdk.out'

# ───────────── create & activate venv ─────────


# (activation moved below)

if (-not $offline) {
  if (-not (Test-Path '.\.venv\Scripts\Activate.ps1')) {
    Write-Host 'Creating Python virtual environment (.venv)...' -ForegroundColor Yellow
    & $PYTHON -m venv .venv
  }
  Write-Host 'Activating virtual environment...' -ForegroundColor Cyan
  . .\.venv\Scripts\Activate.ps1
} else {
  Write-Host 'Offline mode: using current Python environment (no venv activation).' -ForegroundColor Yellow
}

if (-not $offline) {
  Write-Host 'Installing backend requirements...' -ForegroundColor Yellow
  & $PYTHON -m pip install -r .\requirements.txt
} else {
  Write-Host 'Offline mode detected; skipping dependency installation.' -ForegroundColor Yellow
}

# ───────────── env + defaults (PS 5.1) ────────
$env:ALLOTMINT_ENV = Get-ConfigValue $cfg @('server','app_env') 'local'
$env:DATA_ROOT = Coalesce $env:DATA_ROOT (Coalesce $cfg.paths.data_root 'data')
$port      = Get-ConfigValue $cfg @('server','uvicorn_port') $Port
$logConfig = Get-ConfigValue $cfg @('paths','log_config') 'backend/logging.ini'
$resolvedLogConfig = $null
if (Test-Path $logConfig) {
  $content = Get-Content $logConfig -Raw
  if ($content -match '\[loggers\]' -and $content -match '\[formatters\]') {
    $resolvedLogConfig = $logConfig
  } else {
    Write-Host "Log config '$logConfig' missing [loggers] or [formatters]; using Uvicorn default" -ForegroundColor Yellow
  }
} else {
  Write-Host "Log config '$logConfig' not found; using Uvicorn default" -ForegroundColor Yellow
}
$reloadRaw = Get-ConfigValue $cfg @('server','reload') $true
$reload    = [bool]$reloadRaw

if ($env:DATA_BUCKET) {
  if (Get-HasCommand 'aws') {
    Write-Host "Syncing data from s3://$env:DATA_BUCKET/" -ForegroundColor Yellow
    aws s3 sync "s3://$env:DATA_BUCKET/" data/ | Out-Null
  } else {
    Write-Host "AWS CLI not found; skipping data sync from s3://$env:DATA_BUCKET/" -ForegroundColor Yellow
  }
} else {
  Write-Host "DATA_BUCKET not set; skipping data sync" -ForegroundColor Yellow
}

# ───────────── start server ───────────────────
Write-Host "Starting AllotMint Local API on http://localhost:$port ..." -ForegroundColor Green

$arguments = @(
  'backend.local_api.main:app',
  '--reload-dir', 'backend',
  '--port', $port,
  '--app-dir', '.'
)
if ($resolvedLogConfig) { $arguments += @('--log-config', $resolvedLogConfig) }
if ($reload) { $arguments += '--reload' }

& $PYTHON -m uvicorn @arguments
