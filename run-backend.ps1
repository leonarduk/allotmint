Param(
    [int]$Port = 8000
)

$env:ALLOTMINT_OFFLINE_MODE = $false

# or leave it unset to allow dependency installation.
$ErrorActionPreference = 'Stop'

# -------- Configuration --------
# Set $env:ALLOTMINT_OFFLINE_MODE = 'true' before running to enable offline mode,
# --------------------------------

# repo root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

# create venv if missing
if (-not (Test-Path '.\.venv\Scripts\Activate.ps1')) {
    Write-Host 'Creating Python virtual environment (.venv)...' -ForegroundColor Yellow
    python -m venv .venv
}

# activate
Write-Host 'Activating virtual environment...' -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

# determine offline status
$offline = $false
if ($env:ALLOTMINT_OFFLINE_MODE -and $env:ALLOTMINT_OFFLINE_MODE.ToLower() -eq 'true') {
    $offline = $true
}

if (-not $offline) {
    Write-Host 'Installing backend requirements...' -ForegroundColor Yellow
    python -m pip install --upgrade pip
    python -m pip install -r .\requirements.txt
} else {
    Write-Host 'Offline mode detected; skipping dependency installation.' -ForegroundColor Yellow
}

# env
$env:ALLOTMINT_ENV = 'local'

# run
Write-Host "Starting AllotMint Local API on http://localhost:$Port ..." -ForegroundColor Green
python -m uvicorn backend.local_api.main:app --reload --port $Port --log-level info --app-dir .
