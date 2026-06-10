#!/usr/bin/env bash
# Run key pre-deploy validation checks locally before pushing a release tag.
# Checks that require AWS credentials are skipped gracefully when AWS_ACCESS_KEY_ID is unset.
#
# Note: AWS_ACCESS_KEY_ID is used as a proxy for "has AWS credentials". Engineers using
# aws sso login or ~/.aws/credentials profiles without this var set will see AWS checks
# skipped; export AWS_ACCESS_KEY_ID manually or comment out the guard to override.
#
# -e is intentionally omitted: every command is guarded by an explicit if/else so the
# script always runs all checks and accumulates failures rather than aborting on the first.
set -uo pipefail

# Always run from the repository root regardless of where the script is invoked from.
cd "$(dirname "$0")/../.." || exit 1

PASS=0
FAIL=0
SKIP=0

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP: $1"; SKIP=$((SKIP + 1)); }

# 0. Deployment environment variable validation
echo ""
echo "=== 0. Deployment environment variable validation ==="
if bash scripts/bash/validate-deployment-env.sh; then
    pass "deployment environment variables"
else
    fail "deployment environment variables"
fi

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
    cdk_diff_output=$(mktemp)
    (cd cdk && npx cdk diff BackendLambdaStack StaticSiteStack -c prod=true --method=changeset) | tee "$cdk_diff_output"
    cdk_diff_exit=${PIPESTATUS[0]}
    if [[ $cdk_diff_exit -ne 0 ]]; then
        fail "CDK diff"
    elif ! python3 scripts/check_cdk_diff_iam_removals.py "$cdk_diff_output"; then
        fail "CDK diff (removes an IAM Allow grant for the deploy role — see #3741)"
    else
        pass "CDK diff"
    fi
    rm -f "$cdk_diff_output"
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
        AWS_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}"
        AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
        BUCKET_ARN="arn:aws:s3:::${BUCKET_ID}"
        # Include Lambda and CloudFormation ARNs so those action simulations are meaningful.
        LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT}:function:*"
        CFN_ARN="arn:aws:cloudformation:${AWS_REGION}:${AWS_ACCOUNT}:stack/BackendLambdaStack/*"
        # Map each action to its canonical resource ARN to avoid IAM returning
        # "notApplicable" for mismatched action/resource pairs.  notApplicable means
        # IAM could not evaluate the combination (e.g. a wildcard ARN that doesn't match
        # the action's resource type) — it is treated as a warning, not a hard failure,
        # since it does not indicate the action is actually denied.
        declare -A ACTION_RESOURCES=(
            ["s3:GetObject"]="${BUCKET_ARN}/*"
            ["s3:ListBucket"]="${BUCKET_ARN}"
            ["lambda:InvokeFunction"]="${LAMBDA_ARN}"
            ["cloudformation:CreateChangeSet"]="${CFN_ARN}"
            ["cloudformation:DescribeChangeSet"]="${CFN_ARN}"
            ["cloudformation:DeleteChangeSet"]="${CFN_ARN}"
        )
        sim_failed=0
        sim_unavailable=0
        for ACTION in "${!ACTION_RESOURCES[@]}"; do
            RESOURCE="${ACTION_RESOURCES[$ACTION]}"
            # Capture stdout+stderr together; preserve exit code separately so raw_result
            # always contains the real AWS CLI output (the || idiom would overwrite it).
            raw_result=$(aws iam simulate-principal-policy \
                --policy-source-arn "$GITHUB_DEPLOY_ROLE_ARN" \
                --action-names "$ACTION" \
                --resource-arns "$RESOURCE" \
                --query "EvaluationResults[0].EvalDecision" \
                --output text 2>&1)
            aws_exit=$?
            # Distinguish four cases:
            # 1. The caller is not authorised to call iam:SimulatePrincipalPolicy → warn and skip
            #    so a bootstrap deploy that grants the permission can still proceed (#3209).
            #    Use -E (ERE) for portable | alternation; BRE \| is not reliable on BSD grep.
            # 2. Any other non-zero exit (unexpected error) → hard-fail.
            # 3. notApplicable → warn (IAM could not evaluate the action/resource combination;
            #    this is not a denial and the per-action resource map should prevent it).
            # 4. Any other non-"allowed" decision (explicitDeny/implicitDeny) → hard-fail.
            if echo "$raw_result" | grep -qiE "not authorized to perform.*iam:SimulatePrincipalPolicy|iam:SimulatePrincipalPolicy.*not authorized"; then
                echo "::warning::simulate-principal-policy unavailable for $ACTION — deploy role lacks iam:SimulatePrincipalPolicy. Run scripts/bash/bootstrap-deploy-role.sh to grant it."
                echo "  AWS response: $raw_result" >&2
                sim_unavailable=1
            elif [ "$aws_exit" -ne 0 ]; then
                echo "::error::simulate-principal-policy failed for $ACTION with an unexpected error."
                echo "  AWS response: $raw_result" >&2
                sim_failed=1
            else
                # Extract the decision by matching only the known EvalDecision token values.
                result="$(echo "$raw_result" | grep -m1 -E '^(allowed|explicitDeny|implicitDeny|notApplicable)$')"
                if [ "$result" = "allowed" ]; then
                    : # pass — no action needed
                elif [ "$result" = "notApplicable" ]; then
                    echo "::warning::$ACTION returned notApplicable on $RESOURCE — IAM could not evaluate this action/resource combination. Check resource ARN mapping."
                    sim_unavailable=1
                else
                    echo "::error::$ACTION not allowed on $RESOURCE (got: ${result:-<no decision token found>})"
                    echo "  AWS response: $raw_result" >&2
                    sim_failed=1
                fi
            fi
        done
        if [ "$sim_failed" -eq 1 ]; then
            fail "IAM permission simulation"
        elif [ "$sim_unavailable" -eq 1 ]; then
            echo "::warning::IAM simulation skipped or incomplete — see warnings above."
            skip "IAM permission simulation (check warnings above)"
        else
            pass "IAM permission simulation"
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
