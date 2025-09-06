param(
    [Parameter(Mandatory=$false)][string]$DataBucket
)

$ErrorActionPreference = 'Stop'

# Navigate to repository root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

try {
  # Move into CDK directory
  Set-Location (Join-Path $SCRIPT_DIR 'cdk')

  # Ensure CDK CLI is available
  if (-not (Get-Command 'cdk' -ErrorAction SilentlyContinue)) {
    Write-Error 'AWS CDK CLI not found. Install it and try again.'
    exit 1
  }

  # Determine data bucket
  if (-not $DataBucket) {
    $DataBucket = $env:DATA_BUCKET
  }
  if (-not $DataBucket) {
    Write-Error 'DATA_BUCKET must be provided via -DataBucket parameter or DATA_BUCKET environment variable.'
    exit 1
  }

  # Bootstrap environment (safe to run multiple times)
  cdk bootstrap
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  # Deploy backend and frontend stacks
  cdk deploy BackendLambdaStack StaticSiteStack -c deploy_backend=true -c data_bucket=$DataBucket
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
catch {
  Write-Error $_
  exit 1
}
finally {
  # Return to repository root
  Set-Location $SCRIPT_DIR
}

