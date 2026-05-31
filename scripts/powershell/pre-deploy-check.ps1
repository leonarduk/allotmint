# Run key pre-deploy validation checks locally before pushing a release tag.
# Checks that require AWS credentials are skipped gracefully when AWS_ACCESS_KEY_ID is unset.
$ErrorActionPreference = 'Continue'

$Pass = 0
$Fail = 0

function Write-Pass($msg) { Write-Host "PASS: $msg" -ForegroundColor Green; $script:Pass++ }
function Write-Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; $script:Fail++ }
function Write-Skip($msg) { Write-Host "SKIP: $msg" -ForegroundColor Yellow }

# 1. Dependency dry-run
Write-Host "`n=== 1. Dependency dry-run ==="
python -m venv "$env:TEMP\pre-deploy-venv" | Out-Null
& "$env:TEMP\pre-deploy-venv\Scripts\pip.exe" install --dry-run -r backend/requirements.txt -q
if ($LASTEXITCODE -eq 0) { Write-Pass "pip dependency dry-run" } else { Write-Fail "pip dependency dry-run" }

# 2. CDK synth + diff
Write-Host "`n=== 2. CDK synth + diff ==="
if (-not $env:AWS_ACCESS_KEY_ID) {
    Write-Skip "CDK diff (requires AWS credentials)"
} elseif (-not $env:GITHUB_DEPLOY_ROLE_ARN -or -not $env:JWT_SECRET -or -not $env:GOOGLE_CLIENT_ID -or -not $env:DATA_BUCKET) {
    Write-Skip "CDK diff (requires GITHUB_DEPLOY_ROLE_ARN, JWT_SECRET, GOOGLE_CLIENT_ID, DATA_BUCKET)"
} else {
    Push-Location cdk
    npx cdk diff BackendLambdaStack StaticSiteStack -c prod=true
    if ($LASTEXITCODE -eq 0) { Write-Pass "CDK diff" } else { Write-Fail "CDK diff" }
    Pop-Location
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
        aws iam simulate-principal-policy `
            --policy-source-arn $env:GITHUB_DEPLOY_ROLE_ARN `
            --action-names s3:GetObject s3:ListBucket lambda:InvokeFunction `
                cloudformation:CreateChangeSet cloudformation:DescribeChangeSet `
                cloudformation:DeleteChangeSet `
            --resource-arns $BucketArn "$BucketArn/*" `
            --query "EvaluationResults[?EvalDecision!='allowed'].{Action:EvalActionName,Decision:EvalDecision}" `
            --output table
        if ($LASTEXITCODE -eq 0) { Write-Pass "IAM permission simulation" } else { Write-Fail "IAM permission simulation" }
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
Push-Location cdk
python -m pytest tests/ -x -q
if ($LASTEXITCODE -eq 0) { Write-Pass "CDK pytest" } else { Write-Fail "CDK pytest" }
Pop-Location

# Summary
Write-Host "`n==============================="
Write-Host "Pre-deploy check summary"
Write-Host "PASS: $Pass  FAIL: $Fail"
Write-Host "==============================="

if ($Fail -gt 0) {
    Write-Host "One or more checks failed. Fix before pushing a release tag." -ForegroundColor Red
    exit 1
}
Write-Host "All checks passed." -ForegroundColor Green
