Param(
  [string[]]$PytestArgs,
  [switch]$Open
)

$ErrorActionPreference = 'Stop'

# Resolve repo root and run from there
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT

function Get-PythonCmd {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $cmd) { $cmd = Get-Command py -ErrorAction SilentlyContinue }
  if (-not $cmd) {
    Write-Host 'Python is required but was not found. Install from https://www.python.org/downloads/' -ForegroundColor Red
    exit 1
  }
  return $cmd.Name
}

$PYTHON = Get-PythonCmd

# Verify dependencies (pytest + coverage). Use coverage directly to avoid pytest-cov dependency.
try { & $PYTHON -m coverage --version | Out-Null }
catch {
  Write-Host 'coverage.py is not installed. Install dev deps first:' -ForegroundColor Yellow
  Write-Host '  pip install -r requirements.txt -r requirements-dev.txt' -ForegroundColor Yellow
  exit 1
}

try { & $PYTHON -m pytest --version | Out-Null }
catch {
  Write-Host 'pytest is not installed. Install dev deps first:' -ForegroundColor Yellow
  Write-Host '  pip install -r requirements.txt -r requirements-dev.txt' -ForegroundColor Yellow
  exit 1
}

# Run tests under coverage, then generate HTML and summary reports
Write-Host '# Running tests with coverage (backend scope via .coveragerc) ...' -ForegroundColor Cyan

& $PYTHON -m coverage erase | Out-Null
& $PYTHON -m coverage run -m pytest @PytestArgs
$exitCode = $LASTEXITCODE

& $PYTHON -m coverage html
& $PYTHON -m coverage report

$report = Join-Path $REPO_ROOT 'htmlcov\index.html'
if (Test-Path $report) {
  Write-Host ("HTML coverage report: {0}" -f (Resolve-Path $report)) -ForegroundColor Green
  if ($Open) {
    Start-Process (Resolve-Path $report)
  }
}

exit $exitCode

