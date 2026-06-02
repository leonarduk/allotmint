#!/usr/bin/env bash
# Validates that all required deployment environment variables are configured.
# This script is used by pre-deploy-check.sh and can be run standalone to diagnose
# missing configuration before attempting a deploy.
#
# Exit codes:
#   0 = all required variables present
#   1 = one or more required variables missing
#   2 = one or more optional variables missing (only if --strict is used)
#
# Usage:
#   bash scripts/bash/validate-deployment-env.sh          # Check required vars
#   bash scripts/bash/validate-deployment-env.sh --strict  # Check required + optional

set -uo pipefail

STRICT="${1:-}"
MISSING_REQUIRED=0
MISSING_OPTIONAL=0
MISSING_AWS=0

check_required() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    local description="$2"

    if [ -z "$var_value" ]; then
        echo "REQUIRED: $var_name is not set"
        echo "  Purpose: $description"
        MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
        return 1
    fi
    echo "OK: $var_name is set"
    return 0
}

check_optional() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    local description="$2"

    if [ -z "$var_value" ]; then
        echo "OPTIONAL: $var_name is not set"
        echo "  Purpose: $description"
        MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
        return 1
    fi
    echo "OK: $var_name is set"
    return 0
}

check_aws() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    local description="$2"

    if [ -z "$var_value" ]; then
        echo "AWS: $var_name is not set"
        echo "  Purpose: $description"
        MISSING_AWS=$((MISSING_AWS + 1))
        return 1
    fi
    echo "OK: $var_name is set"
    return 0
}

echo ""
echo "========================================" 
echo "Deployment Environment Variable Check"
echo "========================================" 

echo ""
echo "=== REQUIRED VARIABLES (for all deployments) ==="
check_required "DATA_BUCKET" "S3 bucket containing account and metadata data"
check_required "JWT_SECRET" "Secret key for JWT token signing in backend"
check_required "GOOGLE_CLIENT_ID" "Google OAuth client ID for authentication"

echo ""
echo "=== AWS CREDENTIALS CHECK ==="
if [ -n "${AWS_ACCESS_KEY_ID:-}" ] || [ -n "${AWS_PROFILE:-}" ] || [ -f ~/.aws/credentials ]; then
    echo "AWS credentials detected (AWS_ACCESS_KEY_ID or AWS_PROFILE set, or ~/.aws/credentials exists)"
    echo ""
    echo "=== AWS VARIABLES (required when deploying to AWS) ==="
    check_aws "AWS_REGION" "AWS region for CDK and Lambda deployment"
    check_aws "GITHUB_DEPLOY_ROLE_ARN" "ARN of IAM role for GitHub Actions deployment"
else
    echo "No AWS credentials detected — AWS-specific checks skipped"
    echo "Set AWS_ACCESS_KEY_ID, AWS_PROFILE, or configure ~/.aws/credentials to enable them"
fi

echo ""
echo "=== OPTIONAL VARIABLES ==="
if [ "$STRICT" = "--strict" ]; then
    check_optional "SMOKE_TEST_USERNAME" "Username for smoke test authentication"
    check_optional "SMOKE_TEST_PASSWORD" "Password for smoke test authentication"
else
    echo "OPTIONAL: Smoke test credentials (run with --strict to enforce)"
    echo "  SMOKE_TEST_USERNAME - Username for smoke test authentication"
    echo "  SMOKE_TEST_PASSWORD - Password for smoke test authentication"
fi

echo ""
echo "========================================" 
echo "Summary"
echo "========================================" 
echo "Missing required: $MISSING_REQUIRED"
echo "Missing optional: $MISSING_OPTIONAL"
echo "Missing AWS variables: $MISSING_AWS"
echo ""

if [ "$MISSING_REQUIRED" -gt 0 ]; then
    echo "ERROR: One or more required variables are missing."
    echo ""
    echo "To fix:"
    echo "1. Export the missing variables in your shell or .env file"
    echo "2. For GitHub Actions, set them as repository secrets or variables"
    echo "3. For local deployment, ensure they are present before running deploy scripts"
    echo ""
    echo "See docs/CONTRIBUTOR_RUNBOOK.md section 'Deployment environment variables' for details."
    exit 1
fi

if [ "$MISSING_AWS" -gt 0 ] && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    echo "ERROR: AWS credentials detected but required AWS variables are missing."
    echo ""
    echo "To fix:"
    echo "1. Set AWS_REGION to your target deployment region"
    echo "2. Set GITHUB_DEPLOY_ROLE_ARN to the IAM role ARN for GitHub Actions"
    echo ""
    echo "See docs/CONTRIBUTOR_RUNBOOK.md section 'Deployment environment variables' for details."
    exit 1
fi

if [ "$MISSING_OPTIONAL" -gt 0 ] && [ "$STRICT" = "--strict" ]; then
    echo "WARNING: Optional variables are missing. Smoke tests may run unauthenticated."
    exit 2
fi

echo "All required variables are present ✓"
exit 0
