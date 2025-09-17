$ErrorActionPreference = 'Continue'

# Determine repository root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
Set-Location $REPO_ROOT

# Validate each python candidate by probing with --version so that we avoid
# launching the linters when the interpreter shim is present but unusable.
$pythonCommand = $null
foreach ($candidate in @('python', 'py')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        try {
            $null = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                $pythonCommand = $candidate
                break
            }
        } catch {
            continue
        }
    }
}

$summary = @()

function Run-Linter {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [scriptblock]$Parser
    )
    Write-Host "Running $Name..." -ForegroundColor Cyan
    try {
        $output = & $Command 2>&1
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Host "$Name failed: $($_.Exception.Message)" -ForegroundColor Yellow
        $script:summary += "$($Name): failed to run ($($_.Exception.Message))"
        return
    }
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        Write-Host "$Name exited with code $exitCode" -ForegroundColor Yellow
        $script:summary += "$($Name): exited with code $exitCode"
        return
    }
    if ($Parser) {
        $parsed = & $Parser $output
        if ($parsed) { $script:summary += $parsed }
    }
}

function Parse-Ruff {
    param([string[]]$Lines)
    foreach ($line in $Lines) {
        if ($line -match '^(.+?:\d+:\d+):\s*(.+)$') {
            "$($matches[1]) $($matches[2])"
        }
    }
}

function Parse-Black {
    param([string[]]$Lines)
    foreach ($line in $Lines) {
        if ($line -match '^would reformat (.+)$') {
            "$($matches[1]):1:1 would reformat"
        }
    }
}

function Parse-ESLint {
    param([string[]]$Lines)
    foreach ($line in $Lines) {
        if ($line -match '^(.+?):(\d+):(\d+):\s*(.+)$') {
            "$($matches[1]):$($matches[2]):$($matches[3]) $($matches[4])"
        }
    }
}

if ($pythonCommand) {
    Run-Linter "ruff" { & $pythonCommand -m ruff check --config backend/pyproject.toml backend tests cdk scripts } ${function:Parse-Ruff}
    Run-Linter "black" { & $pythonCommand -m black --check --config backend/pyproject.toml backend tests cdk scripts } ${function:Parse-Black}
} else {
    $summary += "Python linters skipped: no working python interpreter found"
}

if (Test-Path frontend) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Run-Linter "eslint" {
            Push-Location frontend
            $r = npm run lint --silent -- --format unix
            Pop-Location
            $r
        } ${function:Parse-ESLint}
    } else {
        $summary += "eslint: npm not available"
    }
}

Write-Host "`n===== Lint Summary (copy for Codex) =====" -ForegroundColor Green
if ($summary) {
    $summary | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "No lint issues found." -ForegroundColor Green
}
