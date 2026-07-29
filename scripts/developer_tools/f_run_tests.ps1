# Run the backend test suite from anywhere in the repo (root or
# scripts/developer_tools). Resolve the repo root first so the relative
# paths below (tests, backend, test-results) always point at the right place.
$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    Write-Error "Not in a git repository"
    exit 1
}

Push-Location $repoRoot
try {
    pytest tests --cov=backend --cov-report=html --cov-report=xml --junit-xml=test-results/junit.xml
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
