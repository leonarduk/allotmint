param(
    [string]$Message = $null,
    [string[]]$Files = $null,
    [switch]$NoOllama = $false,
    [string]$Model = $null
)

# Ensure we're in the repo root
$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    Write-Error "Not in a git repository"
    exit 1
}

# Build arguments for the Python script
$pythonArgs = @()

if ($Message) {
    $pythonArgs += "--message", $Message
}

if ($Files -and $Files.Count -gt 0) {
    $pythonArgs += "--files"
    $pythonArgs += $Files
}

if ($NoOllama) {
    $pythonArgs += "--no-ollama"
}

if ($Model) {
    $pythonArgs += "--model", $Model
}

# Run the Python script
python (Join-Path $repoRoot "scripts" "publish_pr.py") @pythonArgs
exit $LASTEXITCODE
