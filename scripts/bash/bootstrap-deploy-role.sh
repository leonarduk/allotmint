#!/usr/bin/env bash
# Run once when the deploy role is first created, and again whenever the
# AllotmintDeployPolicy permissions need to change.
#
# Note on dual management: this script and cdk/stacks/static_site_stack.py
# both grant some of the same permissions. The CDK grant keeps permissions
# current across future cdk deploys. This script is needed to bootstrap the
# role before the first CDK deploy (chicken-and-egg: CDK needs the role to
# have these permissions to deploy, but deploying is what grants them via CDK).
# Running this script after CDK deploys is safe — put-role-policy is idempotent.
#
# Required environment variables:
#   DEPLOY_ROLE_NAME  — short name of the IAM role (not the full ARN)
#   DATA_BUCKET       — physical name of the S3 data bucket
#
# Optional (auto-detected if absent):
#   AWS_ACCOUNT_ID    — 12-digit AWS account ID (resolved via sts get-caller-identity)
#   AWS_REGION        — AWS region (resolved via aws configure get region)
#
# Usage:
#   DEPLOY_ROLE_NAME=allotmint-github-deploy \
#   DATA_BUCKET=my-allotmint-data-bucket \
#   bash scripts/bash/bootstrap-deploy-role.sh

set -euo pipefail

: "${DEPLOY_ROLE_NAME:?DEPLOY_ROLE_NAME must be set to the IAM role short name}"
: "${DATA_BUCKET:?DATA_BUCKET must be set to the S3 data bucket name}"

AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
AWS_REGION="${AWS_REGION:-$(aws configure get region)}"

echo "Attaching AllotmintDeployPolicy to role: ${DEPLOY_ROLE_NAME}"
echo "  Account : ${AWS_ACCOUNT_ID}"
echo "  Region  : ${AWS_REGION}"
echo "  Bucket  : ${DATA_BUCKET}"

policy_document="$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FilterLogEvents",
      "Effect": "Allow",
      "Action": "logs:FilterLogEvents",
      "Resource": [
        "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/lambda/BackendLambdaStack-BackendLambda*",
        "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/lambda/BackendLambdaStack-PriceRefreshLambda*",
        "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/lambda/BackendLambdaStack-TradingAgentLambda*"
      ]
    },
    {
      "Sid": "CdkDiffChangeSets",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateChangeSet",
        "cloudformation:DescribeChangeSet",
        "cloudformation:DeleteChangeSet"
      ],
      "Resource": [
        "arn:aws:cloudformation:${AWS_REGION}:${AWS_ACCOUNT_ID}:stack/BackendLambdaStack/*",
        "arn:aws:cloudformation:${AWS_REGION}:${AWS_ACCOUNT_ID}:stack/StaticSiteStack/*"
      ]
    },
    {
      "Sid": "InvokePriceRefreshLambdaLiveAlias",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:BackendLambdaStack-PriceRefreshLambda*:live"
    },
    {
      "Sid": "ReadPriceSnapshot",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${DATA_BUCKET}/prices/latest_prices.json"
    },
    {
      "Sid": "ListPricesPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${DATA_BUCKET}",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["prices", "prices/*"]
        }
      }
    },
    {
      "Sid": "SimulatePrincipalPolicyForPreflightCheck",
      "Effect": "Allow",
      "Action": "iam:SimulatePrincipalPolicy",
      "Resource": "*"
    }
  ]
}
EOF
)"

aws iam put-role-policy \
  --role-name "${DEPLOY_ROLE_NAME}" \
  --policy-name "AllotmintDeployPolicy" \
  --policy-document "${policy_document}"

echo "AllotmintDeployPolicy attached successfully."
