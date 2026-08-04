param(
    [string]$Message = $null,
    [string[]]$Files = $null,
    # --no-llm is the canonical flag (via the alias on $NoLlm).
    # -NoOllama is kept for backward compatibility only.
    # If both are passed, both --no-ollama and --no-llm are forwarded to the Python CLI;
    # this is acceptable and the CLI handles both flags.
    [switch]$NoOllama = $false,
    [alias("no-llm")]
    [switch]$NoLlm = $false,
    [string]$Model = $null,
    [ValidateSet('local', 'cloud')]
    [string]$ModelSource = $null,
    [switch]$NoPush = $false
)

<#
.SYNOPSIS
Commit local changes (with an LLM-drafted message) and push to origin.

.DESCRIPTION
This script stages, commits, and optionally pushes changes based on CLI arguments.
It uses an LLM for the commit message if available and specified.

.PARAMETER Message
Override the default commit message.

.PARAMETER Files
Specific files to stage (default: all changed files).

.PARAMETER NoOllama
Skip the LLM and use a plain default commit message.

.PARAMETER Model
Ollama model name, only used when --model-source=local (default: OLLAMA_MODEL env var or 'qwen2.5-coder:7b').
ModelSource does not need to be passed alongside Model: the underlying Python script already defaults
model-source to 'local'. Passing -Model with -ModelSource cloud is accepted but ignored, with a warning.

.PARAMETER ModelSource
Specify the source of the model being committed and pushed.
Possible values:
- local: Use a local LLM model.
- cloud: Use a cloud-based LLM model.

.PARAMETER NoPush
Commit only; skip pushing the branch to origin.

.EXAMPLE
.\j_commit_and_push.ps1 -Message "Fix bug" -Files "file1.py", "file2.py"

.EXAMPLE
.\j_commit_and_push.ps1 -NoOllama

.EXAMPLE
.\j_commit_and_push.ps1 -Model "qwen2.5-coder:7b" -ModelSource local

.NOTES
Ensure you're in the repo root when running this script.
#>

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

if ($NoLlm) {
    $pythonArgs += "--no-llm"
}

if ($Model) {
    $pythonArgs += "--model", $Model
}

if ($ModelSource) {
    $pythonArgs += "--model-source", $ModelSource
}

if ($NoPush) {
    $pythonArgs += "--no-push"
}

# Run the Python script
# Nest Join-Path calls so this also works on Windows PowerShell 5.1, whose
# Join-Path lacks the -AdditionalChildPath parameter (PowerShell 6+ only).
$scriptPath = Join-Path (Join-Path (Join-Path (Join-Path $repoRoot "scripts") "developer_tools") "lib") "commit_and_push.py"
python $scriptPath @pythonArgs
exit $LASTEXITCODE
