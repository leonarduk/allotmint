$ErrorActionPreference = 'Stop'

# Determine repository root and navigate to frontend directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
$FRONTEND_DIR = Join-Path $REPO_ROOT 'frontend'

if (-not (Test-Path $FRONTEND_DIR)) {
    throw "Frontend directory not found at: $FRONTEND_DIR"
}

Set-Location $FRONTEND_DIR

Write-Host 'Installing frontend dependencies...' -ForegroundColor Yellow
npm install

$env:VITE_APP_BASE_URL = 'http://localhost:5173'

Write-Host 'Starting frontend development server...' -ForegroundColor Green
npm run dev
