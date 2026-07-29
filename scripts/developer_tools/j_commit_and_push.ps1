param(
    [string]$Message = $null,
    [string[]]$Files = $null,
    [switch]$NoOllama = $false,
    [string]$Model = $null,
    [switch]$NoPush = $false
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

if ($NoPush) {
    $pythonArgs += "--no-push"
}

# Run the Python script
# Nest Join-Path calls so this also works on Windows PowerShell 5.1, whose
# Join-Path lacks the -AdditionalChildPath parameter (PowerShell 6+ only).
$scriptPath = Join-Path (Join-Path $repoRoot "scripts") (Join-Path "developer_tools" "j_commit_and_push.py")
python $scriptPath @pythonArgs
exit $LASTEXITCODE
