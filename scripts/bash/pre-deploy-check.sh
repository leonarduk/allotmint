#!/usr/bin/env bash
# Run key pre-deploy validation checks locally before pushing a release tag.
# Checks that require AWS credentials are skipped gracefully when AWS_ACCESS_KEY_ID is unset.
set -uo pipefail

# Always run from the repository root regardless of where the script is invoked from.
cd "$(dirname "$0")/../.." || exit 1

PASS=0
FAIL=0
SKIP=0

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP: $1"; SKIP=$((SKIP + 1)); }

# 1. Dependency dry-run
echo ""
echo "=== 1. Dependency dry-run ==="
rm -rf /tmp/pre-deploy-venv
if python -m venv /tmp/pre-deploy-venv && /tmp/pre-deploy-venv/bin/pip install --dry-run -r backend/requirements.txt -q; then
    pass "pip dependency dry-run"
else
    fail "pip dependency dry-run"
fi

# 2. CDK synth + diff
# Uses --method=changeset to match deploy-lambda.yml so replacement annotations are visible.
echo ""
echo "=== 2. CDK synth + diff ==="
if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
    skip "CDK diff (requires AWS credentials)"
elif [[ -z "${GITHUB_DEPLOY_ROLE_ARN:-}" || -z "${JWT_SECRET:-}" || -z "${GOOGLE_CLIENT_ID:-}" || -z "${DATA_BUCKET:-}" ]]; then
    skip "CDK diff (requires GITHUB_DEPLOY_ROLE_ARN, JWT_SECRET, GOOGLE_CLIENT_ID, DATA_BUCKET)"
else
    if (cd cdk && npx cdk diff BackendLambdaStack StaticSiteStack -c prod=true --method=changeset); then
        pass "CDK diff"
    else
        fail "CDK diff"
    fi
fi

# 3. IAM permission simulation
echo ""
echo "=== 3. IAM permission simulation ==="
if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
    skip "IAM simulation (requires AWS credentials)"
elif [[ -z "${GITHUB_DEPLOY_ROLE_ARN:-}" ]]; then
    skip "IAM simulation (requires GITHUB_DEPLOY_ROLE_ARN)"
else
    BUCKET_ID=$(aws cloudformation list-stack-resources \
        --stack-name BackendLambdaStack \
        --query "StackResourceSummaries[?starts_with(LogicalResourceId,'PortfolioDataBucket')].PhysicalResourceId|[0]" \
        --output text 2>/dev/null || echo "")
    if [[ -z "$BUCKET_ID" || "$BUCKET_ID" == "None" ]]; then
        skip "IAM simulation (BackendLambdaStack not deployed or PortfolioDataBucket not found)"
    else
        BUCKET_ARN="arn:aws:s3:::${BUCKET_ID}"
        DENIED=$(aws iam simulate-principal-policy \
            --policy-source-arn "$GITHUB_DEPLOY_ROLE_ARN" \
            --action-names s3:GetObject s3:ListBucket lambda:InvokeFunction \
                cloudformation:CreateChangeSet cloudformation:DescribeChangeSet \
                cloudformation:DeleteChangeSet \
            --resource-arns "${BUCKET_ARN}" "${BUCKET_ARN}/*" \
            --query "EvaluationResults[?EvalDecision!='allowed'].EvalActionName" \
            --output text 2>&1)
        if [[ -z "$DENIED" || "$DENIED" == "None" ]]; then
            pass "IAM permission simulation"
        else
            echo "  Denied actions: $DENIED"
            fail "IAM permission simulation"
        fi
    fi
fi

# 4. Backend lint + tests
echo ""
echo "=== 4. Backend lint + tests ==="
if make lint; then
    pass "make lint"
else
    fail "make lint"
fi

if python -m pytest tests/ -x -q; then
    pass "backend pytest"
else
    fail "backend pytest"
fi

# 5. Frontend lint + tests
echo ""
echo "=== 5. Frontend lint + tests ==="
if npm --prefix frontend run lint; then
    pass "frontend lint"
else
    fail "frontend lint"
fi

if npm --prefix frontend run test -- --run; then
    pass "frontend tests"
else
    fail "frontend tests"
fi

# 6. CDK tests
echo ""
echo "=== 6. CDK tests ==="
if (cd cdk && python -m pytest tests/ -x -q); then
    pass "CDK pytest"
else
    fail "CDK pytest"
fi

# Summary
echo ""
echo "==============================="
echo "Pre-deploy check summary"
echo "PASS: $PASS  FAIL: $FAIL  SKIP: $SKIP"
echo "==============================="

if [[ $FAIL -gt 0 ]]; then
    echo "One or more checks failed. Fix before pushing a release tag."
    exit 1
fi
echo "All checks passed."
