Param(
  [string]$BaseUrl = '',
  [switch]$Local
)

$ErrorActionPreference = 'Stop'

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
  Write-Host 'Python is required but was not found.' -ForegroundColor Red
  exit 1
}
$PYTHON = $pythonCmd.Name

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT

if (-not $BaseUrl -or $BaseUrl -eq '') {
  if ($Local) {
    $BaseUrl = 'http://localhost:5173'
  } else {
    $BaseUrl = 'https://app.allotmint.io'
  }
}

& $PYTHON 'scripts/generate_sitemap.py' '--base-url' $BaseUrl
