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
| `APP_SECRET_NAME` | Secrets Manager secret name read by backend Lambdas (default `allotmint/app`) |
| `BUDGET_ALERT_EMAIL` | Optional email recipient for the monthly AWS budget alert |

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
on every push to `main` (plus manual `workflow_dispatch`). Prefer merging via
PR and letting CI/CD deploy so the live stack stays aligned with the repository
history.

Before deploying, confirm the deployment environment prerequisites:

- AWS account credentials with IAM permissions for CloudFormation, Lambda, API
  Gateway, S3, CloudFront, and IAM role updates.
- CDK bootstrap completed in the target account/region:
  `cdk bootstrap aws://<account>/<region>`.
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

The script changes into the `cdk/` directory, runs `cdk bootstrap` if
necessary, then deploys `BackendLambdaStack` and `StaticSiteStack` when
`-Backend` is specified.

Alternatively, run the commands manually:

```bash
cd cdk
cdk bootstrap   # once per account/region
DEPLOY_BACKEND=false cdk deploy StaticSiteStack
# or deploy backend and frontend together. Supply the name of your
# data bucket either via environment variable:
DATA_BUCKET=my-data-bucket DEPLOY_BACKEND=true cdk deploy BackendLambdaStack StaticSiteStack
# or as a CDK context parameter:
DEPLOY_BACKEND=true cdk deploy BackendLambdaStack StaticSiteStack -c data_bucket=my-data-bucket
# or deploy every stack managed by app.py:
cdk deploy --all --require-approval never
```

When manually validating drift before a deploy, always run:

```bash
cd cdk
cdk diff --all
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

1. Re-run `cdk diff --all` and confirm intended stack changes are present.
2. Run `cdk deploy --all --require-approval never` and capture the exact failing resource from CloudFormation events.
3. Inspect backend Lambda errors (CloudWatch):

   ```bash
   aws logs tail /aws/lambda/<BackendLambdaPhysicalName> --since 30m --follow
   ```

4. Validate API Gateway connectivity with the `BackendApiUrl` output:

   ```bash
   aws cloudformation describe-stacks --stack-name BackendLambdaStack \
     --query "Stacks[0].Outputs[?OutputKey=='BackendApiUrl'].OutputValue" --output text
   curl -fsSL "<BackendApiUrl>docs" >/dev/null
   ```

5. Validate static frontend output with `DistributionDomain`:

   ```bash
   aws cloudformation describe-stacks --stack-name StaticSiteStack \
     --query "Stacks[0].Outputs[?OutputKey=='DistributionDomain'].OutputValue" --output text
   curl -fsSL "https://<DistributionDomain>" >/dev/null
   ```

6. If the frontend is stale after a successful deploy, run CloudFront invalidation (`/*`).
