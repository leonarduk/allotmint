$ErrorActionPreference = 'Stop'

# Determine repository root and navigate to frontend directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Locate repository root whether script lives in repo root or a subdirectory
if (Test-Path (Join-Path $scriptDir 'frontend')) {
    $repoRoot = $scriptDir
} elseif (Test-Path (Join-Path (Split-Path -Parent $scriptDir) 'frontend')) {
    $repoRoot = Split-Path -Parent $scriptDir
} else {
    throw 'Unable to locate the frontend directory.'
}

Set-Location (Join-Path $repoRoot 'frontend')

Write-Host 'Installing frontend dependencies...' -ForegroundColor Yellow
npm install

$env:VITE_APP_BASE_URL = 'http://localhost:5173'

Write-Host 'Starting frontend development server...' -ForegroundColor Green
npm run dev
