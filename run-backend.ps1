Param(
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'

# -------- Configuration --------
# Set offline_mode: true in config.yaml to skip dependency installation
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

# determine offline status from config.yaml
$offline = $false
$configPath = Join-Path $SCRIPT_DIR 'config.yaml'
if (Test-Path $configPath) {
    try {
        $cfg = Get-Content $configPath | ConvertFrom-Yaml
        if ($cfg.offline_mode -eq $true) {
            $offline = $true
        }
    } catch {
        Write-Host 'Warning: failed to parse config.yaml; assuming online mode.' -ForegroundColor Yellow
    }
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
python -m uvicorn backend.local_api.main:app --reload --reload-dir backend --port $Port --log-config backend/logging.ini --app-dir .
