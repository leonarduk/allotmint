$ErrorActionPreference = 'Stop'

# Determine repository root and navigate to frontend directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $SCRIPT_DIR 'frontend')

Write-Host 'Installing frontend dependencies...' -ForegroundColor Yellow
npm install

$env:VITE_APP_BASE_URL = 'http://localhost:5173'

Write-Host 'Starting frontend development server...' -ForegroundColor Green
npm run dev
