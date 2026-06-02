# Validates that all required deployment environment variables are configured.
# This script is used by pre-deploy-check.ps1 and can be run standalone to diagnose
# missing configuration before attempting a deploy.
#
# Exit codes:
#   0 = all required variables present
#   1 = one or more required variables missing
#   2 = one or more optional variables missing (only if -Strict is used)
#
# Usage:
#   pwsh scripts/powershell/validate-deployment-env.ps1          # Check required vars
#   pwsh scripts/powershell/validate-deployment-env.ps1 -Strict  # Check required + optional

param(
    [switch]$Strict = $false
)

$ErrorActionPreference = 'Continue'

$MissingRequired = 0
$MissingOptional = 0
$MissingAws = 0

function Check-Required {
    param(
        [string]$VarName,
        [string]$Description
    )
    $value = Get-Item -Path "env:$VarName" -ErrorAction SilentlyContinue
    if (-not $value) {
        Write-Host "REQUIRED: $VarName is not set" -ForegroundColor Red
        Write-Host "  Purpose: $Description"
        $script:MissingRequired++
        return $false
    }
    Write-Host "OK: $VarName is set" -ForegroundColor Green
    return $true
}

function Check-Optional {
    param(
        [string]$VarName,
        [string]$Description
    )
    $value = Get-Item -Path "env:$VarName" -ErrorAction SilentlyContinue
    if (-not $value) {
        Write-Host "OPTIONAL: $VarName is not set" -ForegroundColor Yellow
        Write-Host "  Purpose: $Description"
        $script:MissingOptional++
        return $false
    }
    Write-Host "OK: $VarName is set" -ForegroundColor Green
    return $true
}

function Check-Aws {
    param(
        [string]$VarName,
        [string]$Description
    )
    $value = Get-Item -Path "env:$VarName" -ErrorAction SilentlyContinue
    if (-not $value) {
        Write-Host "AWS: $VarName is not set" -ForegroundColor Red
        Write-Host "  Purpose: $Description"
        $script:MissingAws++
        return $false
    }
    Write-Host "OK: $VarName is set" -ForegroundColor Green
    return $true
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deployment Environment Variable Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== REQUIRED VARIABLES (for all deployments) ===" -ForegroundColor Cyan
Check-Required "DATA_BUCKET" "S3 bucket containing account and metadata data"
Check-Required "JWT_SECRET" "Secret key for JWT token signing in backend"
Check-Required "GOOGLE_CLIENT_ID" "Google OAuth client ID for authentication"

Write-Host ""
Write-Host "=== AWS CREDENTIALS CHECK ===" -ForegroundColor Cyan
$hasAwsKey = Get-Item -Path "env:AWS_ACCESS_KEY_ID" -ErrorAction SilentlyContinue
$hasAwsProfile = Get-Item -Path "env:AWS_PROFILE" -ErrorAction SilentlyContinue
$awsCredentialsFile = Join-Path $env:USERPROFILE '.aws\credentials'
$hasCredentialsFile = Test-Path $awsCredentialsFile

if ($hasAwsKey -or $hasAwsProfile -or $hasCredentialsFile) {
    Write-Host "AWS credentials detected (AWS_ACCESS_KEY_ID or AWS_PROFILE set, or ~/.aws/credentials exists)"
    Write-Host ""
    Write-Host "=== AWS VARIABLES (required when deploying to AWS) ===" -ForegroundColor Cyan
    Check-Aws "AWS_REGION" "AWS region for CDK and Lambda deployment"
    Check-Aws "GITHUB_DEPLOY_ROLE_ARN" "ARN of IAM role for GitHub Actions deployment"
} else {
    Write-Host "No AWS credentials detected — AWS-specific checks skipped"
    Write-Host "Set AWS_ACCESS_KEY_ID, AWS_PROFILE, or configure ~/.aws/credentials to enable them"
}

Write-Host ""
Write-Host "=== OPTIONAL VARIABLES ===" -ForegroundColor Cyan
if ($Strict) {
    Check-Optional "SMOKE_TEST_USERNAME" "Username for smoke test authentication"
    Check-Optional "SMOKE_TEST_PASSWORD" "Password for smoke test authentication"
} else {
    Write-Host "OPTIONAL: Smoke test credentials (run with -Strict to enforce)" -ForegroundColor Yellow
    Write-Host "  SMOKE_TEST_USERNAME - Username for smoke test authentication"
    Write-Host "  SMOKE_TEST_PASSWORD - Password for smoke test authentication"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Missing required: $MissingRequired"
Write-Host "Missing optional: $MissingOptional"
Write-Host "Missing AWS variables: $MissingAws"
Write-Host ""

if ($MissingRequired -gt 0) {
    Write-Host "ERROR: One or more required variables are missing." -ForegroundColor Red
    Write-Host ""
    Write-Host "To fix:"
    Write-Host "1. Export the missing variables in your shell or .env file"
    Write-Host "2. For GitHub Actions, set them as repository secrets or variables"
    Write-Host "3. For local deployment, ensure they are present before running deploy scripts"
    Write-Host ""
    Write-Host "See docs/CONTRIBUTOR_RUNBOOK.md section 'Deployment environment variables' for details."
    exit 1
}

if (($MissingAws -gt 0) -and $hasAwsKey) {
    Write-Host "ERROR: AWS credentials detected but required AWS variables are missing." -ForegroundColor Red
    Write-Host ""
    Write-Host "To fix:"
    Write-Host "1. Set AWS_REGION to your target deployment region"
    Write-Host "2. Set GITHUB_DEPLOY_ROLE_ARN to the IAM role ARN for GitHub Actions"
    Write-Host ""
    Write-Host "See docs/CONTRIBUTOR_RUNBOOK.md section 'Deployment environment variables' for details."
    exit 1
}

if (($MissingOptional -gt 0) -and $Strict) {
    Write-Host "WARNING: Optional variables are missing. Smoke tests may run unauthenticated." -ForegroundColor Yellow
    exit 2
}

Write-Host "All required variables are present ✓" -ForegroundColor Green
exit 0
