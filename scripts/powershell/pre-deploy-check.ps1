# Run key pre-deploy validation checks locally before pushing a release tag.
# Checks that require AWS credentials are skipped gracefully when AWS_ACCESS_KEY_ID is unset.
$ErrorActionPreference = 'Continue'

# Always run from the repository root regardless of where the script is invoked from.
Set-Location (Join-Path $PSScriptRoot '..\..')

$Pass = 0
$Fail = 0
$Skip = 0

function Write-Pass($msg) { Write-Host "PASS: $msg" -ForegroundColor Green; $script:Pass++ }
function Write-Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; $script:Fail++ }
function Write-Skip($msg) { Write-Host "SKIP: $msg" -ForegroundColor Yellow; $script:Skip++ }

# 1. Dependency dry-run
Write-Host "`n=== 1. Dependency dry-run ==="
$venvPath = Join-Path $env:TEMP 'pre-deploy-venv'
if (Test-Path $venvPath) { Remove-Item -Recurse -Force $venvPath }
python -m venv $venvPath | Out-Null
& "$venvPath\Scripts\pip.exe" install --dry-run -r backend/requirements.txt -q
if ($LASTEXITCODE -eq 0) { Write-Pass "pip dependency dry-run" } else { Write-Fail "pip dependency dry-run" }

# 2. CDK synth + diff
# Uses --method=changeset to match deploy-lambda.yml so replacement annotations are visible.
Write-Host "`n=== 2. CDK synth + diff ==="
if (-not $env:AWS_ACCESS_KEY_ID) {
    Write-Skip "CDK diff (requires AWS credentials)"
} elseif (-not $env:GITHUB_DEPLOY_ROLE_ARN -or -not $env:JWT_SECRET -or -not $env:GOOGLE_CLIENT_ID -or -not $env:DATA_BUCKET) {
    Write-Skip "CDK diff (requires GITHUB_DEPLOY_ROLE_ARN, JWT_SECRET, GOOGLE_CLIENT_ID, DATA_BUCKET)"
} elseif (-not (Test-Path 'cdk')) {
    Write-Fail "CDK diff (cdk/ directory not found — run from repo root)"
} else {
    try {
        Push-Location cdk -ErrorAction Stop
        $cdkArgs = @('cdk', 'diff', 'BackendLambdaStack', 'StaticSiteStack', '-c', 'prod=true', '--method=changeset')
        npx @cdkArgs
        if ($LASTEXITCODE -eq 0) { Write-Pass "CDK diff" } else { Write-Fail "CDK diff" }
    } finally {
        Pop-Location
    }
}

# 3. IAM permission simulation
Write-Host "`n=== 3. IAM permission simulation ==="
if (-not $env:AWS_ACCESS_KEY_ID) {
    Write-Skip "IAM simulation (requires AWS credentials)"
} elseif (-not $env:GITHUB_DEPLOY_ROLE_ARN) {
    Write-Skip "IAM simulation (requires GITHUB_DEPLOY_ROLE_ARN)"
} else {
    $BucketId = aws cloudformation list-stack-resources `
        --stack-name BackendLambdaStack `
        --query "StackResourceSummaries[?starts_with(LogicalResourceId,'PortfolioDataBucket')].PhysicalResourceId|[0]" `
        --output text 2>$null
    if (-not $BucketId -or $BucketId -eq 'None') {
        Write-Skip "IAM simulation (BackendLambdaStack not deployed or PortfolioDataBucket not found)"
    } else {
        $BucketArn = "arn:aws:s3:::$BucketId"
        $iamArgs = @(
            'iam', 'simulate-principal-policy',
            '--policy-source-arn', $env:GITHUB_DEPLOY_ROLE_ARN,
            '--action-names', 's3:GetObject', 's3:ListBucket', 'lambda:InvokeFunction',
                'cloudformation:CreateChangeSet', 'cloudformation:DescribeChangeSet',
                'cloudformation:DeleteChangeSet',
            '--resource-arns', $BucketArn, "$BucketArn/*",
            '--query', "EvaluationResults[?EvalDecision!='allowed'].EvalActionName",
            '--output', 'text'
        )
        $Denied = aws @iamArgs 2>&1
        if (-not $Denied -or $Denied -eq 'None') {
            Write-Pass "IAM permission simulation"
        } else {
            Write-Host "  Denied actions: $Denied"
            Write-Fail "IAM permission simulation"
        }
    }
}

# 4. Backend lint + tests
Write-Host "`n=== 4. Backend lint + tests ==="
make lint
if ($LASTEXITCODE -eq 0) { Write-Pass "make lint" } else { Write-Fail "make lint" }

python -m pytest tests/ -x -q
if ($LASTEXITCODE -eq 0) { Write-Pass "backend pytest" } else { Write-Fail "backend pytest" }

# 5. Frontend lint + tests
Write-Host "`n=== 5. Frontend lint + tests ==="
npm --prefix frontend run lint
if ($LASTEXITCODE -eq 0) { Write-Pass "frontend lint" } else { Write-Fail "frontend lint" }

npm --prefix frontend run test -- --run
if ($LASTEXITCODE -eq 0) { Write-Pass "frontend tests" } else { Write-Fail "frontend tests" }

# 6. CDK tests
Write-Host "`n=== 6. CDK tests ==="
if (-not (Test-Path 'cdk')) {
    Write-Fail "CDK pytest (cdk/ directory not found — run from repo root)"
} else {
    try {
        Push-Location cdk -ErrorAction Stop
        python -m pytest tests/ -x -q
        if ($LASTEXITCODE -eq 0) { Write-Pass "CDK pytest" } else { Write-Fail "CDK pytest" }
    } finally {
        Pop-Location
    }
}

# Summary
Write-Host "`n==============================="
Write-Host "Pre-deploy check summary"
Write-Host "PASS: $Pass  FAIL: $Fail  SKIP: $Skip"
Write-Host "==============================="

if ($Fail -gt 0) {
    Write-Host "One or more checks failed. Fix before pushing a release tag." -ForegroundColor Red
    exit 1
}
Write-Host "All checks passed." -ForegroundColor Green
