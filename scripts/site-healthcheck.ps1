#!/usr/bin/env pwsh
$scriptPath = Join-Path $PSScriptRoot 'site_healthcheck.py'
python $scriptPath @args
if ($LASTEXITCODE -ne 0) {
    Write-Error "Site health check failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
