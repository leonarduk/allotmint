Param(
  [string[]]$PytestArgs,
  [switch]$Open
)

$ErrorActionPreference = 'Stop'

# Resolve repo root and run from there
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT

function Resolve-Python {
  # Prefer project venv if present
  $venvPython = Join-Path $REPO_ROOT '.venv\Scripts\python.exe'
  if (Test-Path $venvPython) { return $venvPython }

  # Next prefer the Windows Python launcher
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return 'py' }

  # Fallback to python; avoid WindowsApps (Microsoft Store) shim
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    $p = $python.Path
    if ($p -and ($p -notmatch '\\WindowsApps\\python.exe$')) { return $p }
  }
  return $null
}

$PYTHON = Resolve-Python
if (-not $PYTHON) {
  Write-Host 'Python not found.' -ForegroundColor Red
  Write-Host 'Install Python (https://www.python.org/downloads/) or create a venv:' -ForegroundColor Yellow
  Write-Host '  py -3 -m venv .venv; . .\\.venv\\Scripts\\Activate.ps1' -ForegroundColor Yellow
  Write-Host 'Then install deps: pip install -r requirements.txt -r requirements-dev.txt' -ForegroundColor Yellow
  Write-Host 'Tip: Disable Windows "App execution aliases" for Python to avoid the Microsoft Store shim.' -ForegroundColor Yellow
  exit 1
}

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

$exitCode = 1
$previousErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  & $PYTHON -m coverage run -m pytest -o addopts='' -p no:cov @PytestArgs 2>&1 |
    Tee-Object -Variable testOutput
  $exitCode = $LASTEXITCODE
}
finally {
  $ErrorActionPreference = $previousErrorActionPreference
}

& $PYTHON -m coverage html
& $PYTHON -m coverage report

$report = Join-Path $REPO_ROOT 'htmlcov\index.html'
if (Test-Path $report) {
  Write-Host ("HTML coverage report: {0}" -f (Resolve-Path $report)) -ForegroundColor Green
  if ($Open) {
    Start-Process (Resolve-Path $report)
  }
}

if ($exitCode -eq 0) {
  Write-Host "All tests passed." -ForegroundColor Green
}

$failurePattern = 'FAILURES'
$summaryPattern = 'short test summary info'
if ($exitCode -ne 0 -and $testOutput) {
  $summaryStart = $testOutput | Select-String -Pattern $summaryPattern | Select-Object -First 1
  if ($summaryStart) {
    $startIndex = $summaryStart.LineNumber
    $summaryLines = $testOutput[$startIndex..($testOutput.Count - 1)] |
      Select-String -Pattern '^FAILED'
    if ($summaryLines) {
      Write-Host 'Failed tests summary:' -ForegroundColor Red
      $summaryLines | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
    }
  }
  $failureStart = $testOutput | Select-String -Pattern $failurePattern | Select-Object -First 1
  if ($failureStart) {
    $startIndex = $failureStart.LineNumber - 1
    $testOutput[$startIndex..($testOutput.Count - 1)] | ForEach-Object { Write-Host $_ -ForegroundColor Red }
  }
}

exit $exitCode

