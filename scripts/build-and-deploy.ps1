[CmdletBinding()]
Param(
  [switch]$Backend,
  [string]$DataBucket
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$frontendDir = Join-Path $repoRoot 'frontend'
$deployScript = Join-Path $scriptDir 'deploy-to-AWS.ps1'

if (-not (Test-Path $frontendDir)) {
  throw "Frontend directory not found at $frontendDir"
}

Push-Location $frontendDir
try {
  if ([string]::IsNullOrWhiteSpace($env:VITE_APP_BASE_URL)) {
    $defaultBaseUrl = 'https://app.allotmint.io'
    Write-Host "VITE_APP_BASE_URL is not set. Defaulting to $defaultBaseUrl. Set VITE_APP_BASE_URL to override." -ForegroundColor Yellow
    $env:VITE_APP_BASE_URL = $defaultBaseUrl
  }
  Write-Host 'Running `npm run build` in the frontend workspace...' -ForegroundColor Cyan
  npm run build
  if ($LASTEXITCODE -ne 0) {
    throw "npm run build failed with exit code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

$deployArgs = @{}
if ($Backend.IsPresent) {
  $deployArgs['Backend'] = $true
}
if ($PSBoundParameters.ContainsKey('DataBucket')) {
  $deployArgs['DataBucket'] = $DataBucket
}

Write-Host 'Starting AWS deployment via deploy-to-AWS.ps1...' -ForegroundColor Cyan
& $deployScript @deployArgs

