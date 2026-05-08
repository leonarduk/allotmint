# Deployment Guide

## Environment variables

Copy `.env.example` to `.env` and supply the following values:

| Variable | Purpose |
| --- | --- |
| `ALPHA_VANTAGE_KEY` | API key for market data |
| `SNS_TOPIC_ARN` | Optional SNS topic for alerts |
| `TELEGRAM_BOT_TOKEN` | Optional Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | Telegram chat for alerts |
| `API_TOKEN` | Token securing sensitive routes |
| `OPENAI_API_KEY` | Optional key for OpenAI features |
| `ANTHROPIC_API_KEY` | Optional key for Anthropic-powered PR review workflows |
| `DATA_ROOT` | Base directory for local data; overrides `paths.data_root` in `config.yaml` |
| `DATA_BUCKET` | S3 bucket holding account data when deploying the backend. May also be supplied via the script's `-DataBucket` parameter |
| `METADATA_BUCKET` | Bucket containing instrument metadata |
| `METADATA_PREFIX` | Prefix within the metadata bucket |
| `GOOGLE_AUTH_ENABLED` | Toggle Google sign‑in |
| `GOOGLE_CLIENT_ID` | OAuth client ID when Google sign‑in is enabled |
| `JWT_SECRET` | Secret used to sign and verify JWT tokens |
| `BUDGET_ALERT_EMAIL` | Optional email recipient for the monthly AWS budget alert |

## GitHub Actions secrets required for AWS deployment

The deploy workflow (`deploy-lambda.yml`) reads the following values from
GitHub Actions secrets at synth time and injects them as Lambda environment
variables. Add them under **Settings → Secrets and variables → Actions →
New repository secret** before triggering a deploy.

| Secret name | New? | How to obtain |
| --- | --- | --- |
| `AWS_REGION` | Pre-existing | Your target AWS region (e.g. `eu-west-1`) |
| `AWS_ROLE_TO_ASSUME` | Pre-existing | ARN of the IAM role the workflow assumes for CDK deployment |
| `DATA_BUCKET` | Pre-existing | Name of the S3 bucket holding account data |
| `JWT_SECRET` | **Required since #2838** | Random string used to sign JWTs — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GOOGLE_CLIENT_ID` | **Required since #2838** | OAuth client ID from Google Cloud Console (ends in `.apps.googleusercontent.com`) |

The CDK stack (`cdk/stacks/backend_lambda_stack.py`) raises a `ValueError`
at synth time if `JWT_SECRET` or `GOOGLE_CLIENT_ID` is absent, failing the
deploy step immediately with a clear message rather than deploying a broken
Lambda.

**Migrating from the Secrets Manager approach** (pre-#2838): `APP_SECRET_NAME`
and the `allotmint/app` Secrets Manager secret are no longer used. Remove
`APP_SECRET_NAME` from any existing GitHub Actions secrets or local `.env`
files and add `JWT_SECRET` and `GOOGLE_CLIENT_ID` directly instead.

The advisory AI review workflows run on pull request `opened`, `reopened`, and `synchronize`
events. They require `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` to be configured as GitHub
repository secrets if you want review comments to be posted, but they remain advisory-only and
use `continue-on-error` so review outages do not block merges.

## API rate limiting

The backend throttles requests per client using SlowAPI. The default limit is
60 requests per minute. Adjust `rate_limit_per_minute` under the `server`
section of `config.yaml` to raise or lower the limit for each environment:

```yaml
server:
  rate_limit_per_minute: 120  # allow 120 requests/minute
```

Higher values are useful for local development or trusted environments, while
lower limits help protect production resources.

## Sync external data store

Account and instrument files are managed in a separate repository. Clone it
next to this project or pull the latest changes before running the backend:

```bash
# first time
git clone git@github.com:your-org/allotmint-data.git data
# fetch updates
cd data && git pull
```

For local runs, point the backend at the checkout by setting ``DATA_ROOT`` or
``accounts_root`` in ``config.yaml``:

```bash
DATA_ROOT=$(pwd)/data
```

In AWS, specify the S3 buckets instead:

```bash
DATA_BUCKET=my-data-bucket
METADATA_BUCKET=my-metadata-bucket
METADATA_PREFIX=instruments/
```

### Updating data

Commit and push changes in the data repository for local development:

```bash
cd data
git add accounts/alice/trades.csv
git commit -m "Update Alice trades"
git push
```

To update the S3 bucket, sync the local data and ensure your IAM role allows
``s3:PutObject`` and ``s3:DeleteObject`` on the target paths:

```bash
aws s3 sync data/accounts s3://$DATA_BUCKET/accounts/
```

## Install dependencies

```bash
pip install -r requirements.txt -r requirements-dev.txt
npm ci
```

## Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

## Deploy with AWS CDK

Production deploys are automated through `.github/workflows/deploy-lambda.yml`
on pushed git tags matching `v*`. Tag a commit only when it is ready for
production so CI/CD deploys the exact tagged revision.

Before deploying, confirm the deployment environment prerequisites:

- AWS account credentials with IAM permissions for CloudFormation, Lambda, API
  Gateway, S3, CloudFront, and IAM role updates.
- CDK bootstrap completed in the target account/region:
  `npx cdk bootstrap aws://<account>/<region>`.
- AWS CLI configured (`aws configure`, named profile, or environment
  variables).
- Python 3.11+ and Node.js 18+ available in local deployment environments
  (CI/CD workflows use Python 3.12).

Run the helper script from the repository root to bootstrap the environment.
When deploying the backend, provide the S3 bucket for account data either via
the `-DataBucket` parameter or by setting `DATA_BUCKET`:

CDK writes synthesized templates to `../.cdk.out`, a directory outside the
repository root that is ignored by git.

```powershell
# Deploy backend and frontend stacks
./scripts/deploy-to-AWS.ps1 -Backend -DataBucket my-bucket

# Deploy only the frontend stack
./scripts/deploy-to-AWS.ps1
```

The script changes into the `cdk/` directory, installs the repo-pinned CDK CLI if
necessary, then deploys `BackendLambdaStack` and `StaticSiteStack` when
`-Backend` is specified.

Alternatively, run the commands manually:

```bash
cd cdk
npx cdk bootstrap   # once per account/region
DEPLOY_BACKEND=false npx cdk deploy StaticSiteStack
# or deploy backend and frontend together. Supply the name of your
# data bucket either via environment variable:
DATA_BUCKET=my-data-bucket DEPLOY_BACKEND=true npx cdk deploy BackendLambdaStack StaticSiteStack
# or as a CDK context parameter:
DEPLOY_BACKEND=true npx cdk deploy BackendLambdaStack StaticSiteStack -c data_bucket=my-data-bucket
# or deploy every stack managed by app.py:
npx cdk deploy --all --require-approval never
```

When manually validating drift before a deploy, always run:

```bash
cd cdk
npx cdk diff --all
```

`BackendLambdaStack` now includes:
- an S3 data bucket with versioning, SSE-S3 encryption, and non-current object expiry,
- one-week CloudWatch log retention for backend/scheduled Lambdas,
- a CloudWatch alarm on backend Lambda errors,
- a monthly AWS Budget resource (default 5 USD, optionally with email alert),
- and Secrets Manager read permissions (`secretsmanager:GetSecretValue`) for all backend Lambdas.

## CloudFront cache invalidation

If static files are updated without redeploying the stack, invalidate the distribution cache:

```bash
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```

## Deployment troubleshooting checklist

If deployment fails or the live environment does not match local behavior:

1. Re-run `npx cdk diff --all` and confirm intended stack changes are present.
2. Run `npx cdk deploy --all --require-approval never` and capture the exact failing resource from CloudFormation events.
3. Inspect backend Lambda errors (CloudWatch). Lambda functions in this stack use
   explicit CDK-managed log groups, so read the deployed log group name from the
   stack outputs instead of assuming the `/aws/lambda/<function-name>` convention:

   ```bash
   BACKEND_LOG_GROUP=$(aws cloudformation describe-stacks --stack-name BackendLambdaStack \
     --query "Stacks[0].Outputs[?OutputKey=='BackendLambdaLogGroupName'].OutputValue" --output text)
   aws logs tail "$BACKEND_LOG_GROUP" --since 30m --follow
   ```

   The scheduled Lambdas expose the same discoverability outputs as
   `PriceRefreshLambdaLogGroupName` and `TradingAgentLambdaLogGroupName`.

4. Validate API Gateway connectivity with the `BackendApiUrl` output:

   ```bash
   aws cloudformation describe-stacks --stack-name BackendLambdaStack \
     --query "Stacks[0].Outputs[?OutputKey=='BackendApiUrl'].OutputValue" --output text
   curl -fsSL "<BackendApiUrl>/docs" >/dev/null
   ```

5. Validate static frontend output and the Cognito UI gate outputs:

   ```bash
   aws cloudformation describe-stacks --stack-name StaticSiteStack \
     --query "Stacks[0].Outputs[?OutputKey=='DistributionDomain'].OutputValue" --output text
   aws cloudformation describe-stacks --stack-name StaticSiteStack \
     --query "Stacks[0].Outputs[?starts_with(OutputKey, 'UiAuth')].[OutputKey,OutputValue]" \
     --output table
   ```

   Create or invite at least one administrator-approved user in the emitted
   Cognito user pool before sharing the CloudFront URL; self sign-up is disabled.
   Browser validation should now redirect unauthenticated visitors to Cognito
   instead of returning a bare HTTP 200 for the dashboard.

6. If the frontend is stale after a successful deploy, run CloudFront invalidation (`/*`).
