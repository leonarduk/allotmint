Param(
  [switch]$Backend,
  [string]$DataBucket
)

$ErrorActionPreference = 'Stop'

# Ensure Python is available (try `python` then `py`)
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
  Write-Host 'Python is required but was not found. Install it from https://www.python.org/downloads/' -ForegroundColor Red
  exit 1
}
$PYTHON = $pythonCmd.Name

# Determine repository root and navigate to CDK directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

# Place synthesized CDK templates outside the repository
$env:CDK_OUTDIR = Join-Path $SCRIPT_DIR '..\.cdk.out'

Set-Location (Join-Path $SCRIPT_DIR 'cdk')

if ($Backend) {
  if (-not $env:DATA_BUCKET -and -not $DataBucket) {
    Write-Host 'Provide the S3 bucket for account data via -DataBucket or DATA_BUCKET environment variable.' -ForegroundColor Red
    exit 1
  }
  if ($DataBucket) {
    $env:DATA_BUCKET = $DataBucket
  }
  if (-not (Test-Path 'data') -or -not (Get-ChildItem 'data' -ErrorAction SilentlyContinue)) {
    Write-Host 'Data directory missing; syncing...' -ForegroundColor Yellow
    bash scripts/sync_data.sh
  }
  Set-Location (Join-Path $SCRIPT_DIR 'cdk')
  Write-Host 'Deploying backend and frontend stacks to AWS...' -ForegroundColor Green
  $env:DEPLOY_BACKEND = 'true'
  cdk deploy BackendLambdaStack StaticSiteStack
} else {
  Set-Location (Join-Path $SCRIPT_DIR 'cdk')
  Write-Host 'Deploying frontend stack to AWS...' -ForegroundColor Green
  $env:DEPLOY_BACKEND = 'false'
  cdk deploy StaticSiteStack

}
