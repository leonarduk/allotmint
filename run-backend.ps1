Param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

# repo root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

# create venv if missing
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}

# activate
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

# install deps (always)
Write-Host "Installing backend requirements..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements.txt

# env
$env:ALLOTMINT_ENV = "local"
$env:ALLOTMINT_OFFLINE_MODE = "false"

# run
Write-Host "Starting AllotMint Local API on http://localhost:$Port ..." -ForegroundColor Green
python -m uvicorn backend.local_api.main:app --reload --port $Port --log-level info --app-dir .
