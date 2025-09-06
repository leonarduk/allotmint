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
| `DATA_BUCKET` | S3 bucket holding account data when deploying the backend |
| `METADATA_BUCKET` | Bucket containing instrument metadata |
| `METADATA_PREFIX` | Prefix within the metadata bucket |
| `GOOGLE_AUTH_ENABLED` | Toggle Google sign‑in |
| `GOOGLE_CLIENT_ID` | OAuth client ID when Google sign‑in is enabled |

Install dependencies:

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
