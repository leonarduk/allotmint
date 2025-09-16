#Requires -Version 5.0
<#!
.SYNOPSIS
    Installs frontend dependencies and runs the coverage test suite.
.DESCRIPTION
    This script automates the two manual steps required to execute the
    frontend coverage tests:
      1. Install NPM dependencies under the frontend workspace.
      2. Run the coverage script defined in package.json.
    The script can be executed from any location. It resolves the
    repository root based on the script location and ensures the npm
    command is available before proceeding.
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
$frontendPath = Join-Path -Path $repoRoot -ChildPath 'frontend'

if (-not (Test-Path -Path $frontendPath)) {
    throw "Frontend directory not found at '$frontendPath'."
}

Push-Location -Path $frontendPath
try {
    Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
    npm install

    Write-Host 'Running frontend coverage tests...' -ForegroundColor Cyan
    npm run coverage
}
finally {
    Pop-Location
}
