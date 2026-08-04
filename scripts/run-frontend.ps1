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

# Persist dev-server output to logs/frontend.log (ISO-8601 timestamped, one
# line per entry) while still streaming live to the console.
$logsDir = Join-Path $REPO_ROOT 'logs'
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$logFile = Join-Path $logsDir 'frontend.log'

Write-Host 'Starting frontend development server...' -ForegroundColor Green
npm run dev 2>&1 | ForEach-Object {
  $timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  $line = "$timestamp $_"
  Write-Host $_
  Add-Content -Path $logFile -Value $line
}

# Capture npm's exit code immediately after the pipeline. Although
# ForEach-Object is a cmdlet that does not overwrite $LASTEXITCODE,
# capturing it into a named variable is safer and makes intent explicit
# for CI/scripts that check the exit code.
$npmExitCode = $LASTEXITCODE
exit $npmExitCode
