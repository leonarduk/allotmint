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
| `DATA_ROOT` | Base directory for local data; overrides `paths.data_root` in `config.yaml` |
| `DATA_BUCKET` | S3 bucket holding account data when deploying the backend. May also be supplied via the script's `-DataBucket` parameter |
| `METADATA_BUCKET` | Bucket containing instrument metadata |
| `METADATA_PREFIX` | Prefix within the metadata bucket |
| `GOOGLE_AUTH_ENABLED` | Toggle Google sign‑in |
| `GOOGLE_CLIENT_ID` | OAuth client ID when Google sign‑in is enabled |

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
```

## CloudFront cache invalidation

If static files are updated without redeploying the stack, invalidate the distribution cache:

```bash
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```

