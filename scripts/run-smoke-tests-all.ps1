#Requires -Version 5.0
<#!
.SYNOPSIS
    Run the full smoke test suite (backend + frontend) via npm.
.DESCRIPTION
    Convenience wrapper that can be launched from any working directory.
    It locates the repository root, ensures npm is available, and runs
    `npm run smoke:test:all`, which orchestrates backend HTTP checks and
    the Playwright frontend smoke suite.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Resolve-RepoRoot {
    param(
        [string]$ScriptRoot
    )

    $current = Resolve-Path -Path $ScriptRoot
    while ($current -and -not (Test-Path -Path (Join-Path -Path $current -ChildPath 'package.json'))) {
        $parent = Split-Path -Path $current -Parent
        if (-not $parent -or $parent -eq $current) {
            throw "Unable to locate repository root from '$ScriptRoot'."
        }
        $current = $parent
    }

    return $current
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required but was not found in PATH."
}

$repoRoot = Resolve-RepoRoot -ScriptRoot $PSScriptRoot

Push-Location -Path $repoRoot
$npmExitCode = 0
try {
    $tsxCliGlob = Join-Path -Path $repoRoot -ChildPath 'node_modules/.bin/tsx*'
    if (-not (Test-Path -Path $tsxCliGlob)) {
        Write-Host "Local tsx CLI was not found. Installing Node dev dependencies ..." -ForegroundColor Yellow
        npm install

        if (-not (Test-Path -Path $tsxCliGlob)) {
            throw "Local tsx CLI is still missing after running 'npm install'. Please ensure Node dev dependencies are installed and rerun the script."
        }
    }

    Write-Host 'Running npm run smoke:test:all ...' -ForegroundColor Cyan
    npm run smoke:test:all
    $npmExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
    if ($npmExitCode -ne 0) {
        exit $npmExitCode
    }
}
