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
try {
    Write-Host 'Running npm run smoke:test:all ...' -ForegroundColor Cyan
    npm run smoke:test:all
}
finally {
    Pop-Location
}
