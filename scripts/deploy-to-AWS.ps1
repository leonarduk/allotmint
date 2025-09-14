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

# Determine repository root and key paths
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT  = (Resolve-Path (Join-Path $SCRIPT_DIR '..')).Path
$CDK_DIR    = Join-Path $REPO_ROOT 'cdk'

# Place synthesized CDK templates outside the repository
$env:CDK_OUTDIR = Join-Path $REPO_ROOT '.cdk.out'

if (-not (Test-Path $CDK_DIR)) {
  Write-Host "CDK directory not found at $CDK_DIR" -ForegroundColor Red
  exit 1
}

if ($Backend) {
  if (-not $env:DATA_BUCKET -and -not $DataBucket) {
    Write-Host 'Provide the S3 bucket for account data via -DataBucket or DATA_BUCKET environment variable.' -ForegroundColor Red
    exit 1
  }
  if ($DataBucket) {
    $env:DATA_BUCKET = $DataBucket
  }
  $dataDir = Join-Path $REPO_ROOT 'data'
  if (-not (Test-Path $dataDir) -or -not (Get-ChildItem $dataDir -ErrorAction SilentlyContinue)) {
    Write-Host 'Data directory missing; syncing...' -ForegroundColor Yellow
    $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $bashCmd) {
      Write-Host 'bash not found; required to run sync_data.sh. Install Git Bash or WSL with bash.' -ForegroundColor Red
      exit 1
    }
    $syncScript = Join-Path $REPO_ROOT 'scripts/bash/sync_data.sh'
    if (-not (Test-Path $syncScript)) {
      Write-Host "Sync script not found at $syncScript" -ForegroundColor Red
      exit 1
    }
    Push-Location $REPO_ROOT
    try {
      & $bashCmd.Path $syncScript
    } finally {
      Pop-Location
    }
  }
  Set-Location $CDK_DIR
  Write-Host 'Deploying backend and frontend stacks to AWS...' -ForegroundColor Green
  $env:DEPLOY_BACKEND = 'true'
  $cdkCmd = Get-Command cdk -ErrorAction SilentlyContinue
  if (-not $cdkCmd) {
    Write-Host 'AWS CDK CLI not found. Install via `npm install -g aws-cdk` or use an existing installation.' -ForegroundColor Red
    exit 1
  }
  $effectiveBucket = if ($env:DATA_BUCKET) { $env:DATA_BUCKET } elseif ($DataBucket) { $DataBucket } else { $null }
  if (-not $effectiveBucket) {
    Write-Host 'DATA_BUCKET is required for backend deployment. Provide via -DataBucket or DATA_BUCKET env var.' -ForegroundColor Red
    exit 1
  }
  & $cdkCmd.Path deploy BackendLambdaStack StaticSiteStack -c "data_bucket=$effectiveBucket"
} else {
  Set-Location $CDK_DIR
  Write-Host 'Deploying frontend stack to AWS...' -ForegroundColor Green
  $env:DEPLOY_BACKEND = 'false'
  $cdkCmd = Get-Command cdk -ErrorAction SilentlyContinue
  if (-not $cdkCmd) {
    Write-Host 'AWS CDK CLI not found. Install via `npm install -g aws-cdk` or use an existing installation.' -ForegroundColor Red
    exit 1
  }
  # Provide a context value for data_bucket so the app can instantiate BackendLambdaStack
  $effectiveBucket = if ($env:DATA_BUCKET) { $env:DATA_BUCKET } elseif ($DataBucket) { $DataBucket } else { 'placeholder-bucket' }
  & $cdkCmd.Path deploy StaticSiteStack -c "data_bucket=$effectiveBucket"

}
