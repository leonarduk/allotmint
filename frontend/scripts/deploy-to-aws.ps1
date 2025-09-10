Param(
  [Parameter(Mandatory = $true)][string]$BucketName,
  [Parameter(Mandatory = $false)][string]$DistributionId,
  [Parameter(Mandatory = $false)][string]$Region = $env:AWS_REGION,
  [Parameter(Mandatory = $false)][string]$InvalidatePath = '/*',
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Section($Text) { Write-Host "`n=== $Text ===" -ForegroundColor Cyan }

try {
  Write-Section 'Validating environment'

  if (-not (Test-Path package.json)) {
    throw 'Run this script from the repository root (package.json not found)'
  }

  if (-not $Region) { $Region = 'eu-west-2' }

  $aws = Get-Command aws -ErrorAction SilentlyContinue
  $hasAws = $null -ne $aws
  if (-not $hasAws) {
    Write-Warning 'aws CLI not found on PATH. Will perform a dry run of deploy steps.'
    $DryRun = $true
  }

  Write-Host "AWS Region: $Region"
  Write-Host "S3 Bucket: s3://$BucketName"
  if ($DistributionId) { Write-Host "CloudFront Distribution: $DistributionId" }

  Write-Section 'Building frontend'
  $npm = Get-Command npm -ErrorAction Stop
  & $npm.Path run build

  if (-not (Test-Path dist)) { throw 'Build output folder ./dist not found' }

  Write-Section 'Syncing to S3'
  $syncArgs = @('s3', 'sync', 'dist', "s3://$BucketName/", '--delete', '--region', $Region, '--only-show-errors', '--cache-control', 'public, max-age=300')
  if ($DryRun) {
    Write-Host "DRY RUN: aws $($syncArgs -join ' ')"
  } else {
    & aws @syncArgs
  }

  if ($DistributionId) {
    Write-Section 'Creating CloudFront invalidation'
    $invArgs = @('cloudfront', 'create-invalidation', '--distribution-id', $DistributionId, '--paths', $InvalidatePath)
    if ($DryRun) {
      Write-Host "DRY RUN: aws $($invArgs -join ' ')"
    } else {
      & aws @invArgs | Out-Null
    }
  }

  Write-Section 'Done'
  if ($DryRun) { Write-Host 'Dry run complete. No changes were made.' -ForegroundColor Yellow }
}
catch {
  Write-Error $_.Exception.Message
  exit 1
}

