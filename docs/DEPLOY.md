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
| `GOOGLE_AUTH_ENABLED` | Toggle Google sign-in |
| `GOOGLE_CLIENT_ID` | OAuth client ID when Google sign-in is enabled |
| `JWT_SECRET` | Secret used to sign and verify JWT tokens |
| `BUDGET_ALERT_EMAIL` | Optional email recipient for the monthly AWS budget alert |

## GitHub Actions secrets required for AWS deployment

The deploy workflow (`deploy-lambda.yml`) reads the following values from
GitHub Actions secrets at synth time and injects them as Lambda environment
variables. Add them under **Settings -> Secrets and variables -> Actions ->
New repository secret** before triggering a deploy.

| Secret name | New? | How to obtain |
| --- | --- | --- |
| `AWS_REGION` | Pre-existing | Your target AWS region (e.g. `eu-west-1`) |
| `AWS_ROLE_TO_ASSUME` | Pre-existing | ARN of the IAM role the workflow assumes for CDK deployment |
| `DATA_BUCKET` | Pre-existing | Name of the S3 bucket holding account data |
| `JWT_SECRET` | **Required since #2838** | Random string used to sign JWTs -- generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GOOGLE_CLIENT_ID` | **Required since #2838** | OAuth client ID from Google Cloud Console (ends in `.apps.googleusercontent.com`) |

The CDK stack (`cdk/stacks/backend_lambda_stack.py`) raises a `ValueError`
at synth time if `JWT_SECRET` or `GOOGLE_CLIENT_ID` is absent, failing the
deploy step immediately with a clear message rather than deploying a broken
Lambda.

### Critical: `GITHUB_DEPLOY_ROLE_ARN` environment variable for CDK synth

The CDK stack (`cdk/stacks/backend_lambda_stack.py`) checks for the environment
variable `GITHUB_DEPLOY_ROLE_ARN` during synthesis. **This value must be the
same ARN as `AWS_ROLE_TO_ASSUME`** -- the role the GitHub Actions deploy
workflow assumes -- because that is the principal that needs permission to
invoke the Lambda.

**Purpose:** When `GITHUB_DEPLOY_ROLE_ARN` is set, the CDK stack grants the
GitHub OIDC deploy role permission to invoke the `PriceRefreshLambda` function.
This is used by the "Warm price snapshot" step in the deploy workflow to seed
market prices after each deployment.

**Consequence of omission:** If `GITHUB_DEPLOY_ROLE_ARN` is not set (or
resolves to an empty string) when CDK synthesises the stack, the Lambda invoke
grant is silently omitted at synth time. The CDK deploy will succeed, but the
"Warm price snapshot" workflow step will fail at runtime with a permission
error:
```
An error occurred (AccessDenied) when calling the InvokeFunction operation:
User: arn:aws:iam::...:role/... is not authorized to perform: lambda:InvokeFunction
```

This is the underlying CDK-synth-time behaviour that makes
`GITHUB_DEPLOY_ROLE_ARN` worth understanding -- *whichever* path synthesises
the stack (the GitHub Actions workflow, a local `cdk deploy`, or
`pre-deploy-check.sh`) must supply it. The numbered checklist below explains,
for each path, whether that's handled for you or something you must do
yourself.

**You do not need to add a separate `GITHUB_DEPLOY_ROLE_ARN` secret or
variable in GitHub.** The "Deploy BackendLambdaStack" step in
`.github/workflows/deploy-lambda.yml` maps it directly from the existing
`AWS_ROLE_TO_ASSUME` secret before invoking `cdk deploy`:

```yaml
env:
  GITHUB_DEPLOY_ROLE_ARN: ${{ secrets.AWS_ROLE_TO_ASSUME }}
```

So the only thing required for CI deploys to grant the invoke permission
correctly is that the **pre-existing `AWS_ROLE_TO_ASSUME` secret is configured**
(see the table above). New deployers and fork maintainers should:

1. **Confirm `AWS_ROLE_TO_ASSUME` is set** under **Settings -> Secrets and
   variables -> Actions** (`https://github.com/<owner>/<repo>/settings/secrets/actions`;
   see also GitHub's [guide to using secrets in Actions](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)).

   The workflow guards against an empty value for you, well before
   `cdk deploy` runs. The "Verify required AWS secrets" step
   (`.github/workflows/deploy-lambda.yml`) explicitly checks for an
   empty string -- not just an unset secret -- and fails the run immediately:

   ```bash
   if [ -z "${{ secrets.AWS_ROLE_TO_ASSUME }}${{ vars.AWS_ROLE_TO_ASSUME }}" ]; then
     echo "AWS_ROLE_TO_ASSUME is not configured (set as secret or repository variable)" >&2
     missing=1
   fi
   ```

   A non-empty-but-malformed ARN is caught shortly after, when
   "Configure AWS credentials" fails to assume the role. Both steps run
   well before "Deploy BackendLambdaStack" (where the `GITHUB_DEPLOY_ROLE_ARN`
   mapping above lives), and a failed step halts the job by default -- so a
   missing, empty, or malformed `AWS_ROLE_TO_ASSUME` cannot reach CDK synth
   in CI. As long as `AWS_ROLE_TO_ASSUME` is a valid ARN, the
   `GITHUB_DEPLOY_ROLE_ARN` mapping takes care of the rest -- no additional
   secret needs to be created.

2. **For bootstrap / first-time setup:** Refer to
   `scripts/bash/bootstrap-deploy-role.sh` and GitHub's
   [Configuring OpenID Connect in Amazon Web Services](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
   guide (the OIDC trust relationship documentation referenced in the bootstrap
   script's comments) to create and configure the deploy role before the first
   deploy.

3. **For local CDK synth/deploy or `pre-deploy-check.sh` runs** (i.e. outside
   the GitHub Actions workflow, where the automatic mapping above does not
   apply): export `GITHUB_DEPLOY_ROLE_ARN` yourself before running CDK, set to
   the same ARN as your deploy role:
   `export GITHUB_DEPLOY_ROLE_ARN=<your-role-arn>` (typically
   `arn:aws:iam::123456789012:role/github-oidc-deploy-role`). See
   `docs/CONTRIBUTOR_RUNBOOK.md` for the full list of variables
   `pre-deploy-check.sh` validates.

**Migrating from the Secrets Manager approach** (pre-#2838): `APP_SECRET_NAME`
and the `allotmint/app` Secrets Manager secret are no longer used. Remove
`APP_SECRET_NAME` from any existing GitHub Actions secrets or local `.env`
files and add `JWT_SECRET` and `GOOGLE_CLIENT_ID` directly instead.

### Dummy environment variable format for CDK dry-run CI

The CI dry-run workflow (`.github/workflows/cdk-dry-run.yml`) validates `cdk synth`
using placeholder values for secrets:
- `JWT_SECRET=dummy`
- `GOOGLE_CLIENT_ID=dummy`

These placeholders **must remain non-empty strings**. If you add or modify validation
logic in `backend_lambda_stack.py` (e.g., checking secret length, format, or truthiness),
ensure dummy values still pass. Empty or falsy values will cause `cdk synth` to fail in
CI and block deployment.

For example, `if not jwt_secret:` is safe with the current placeholder — `"dummy"` is truthy
so this guard does not fire. By contrast, `if len(jwt_secret) < 32:` breaks the dry-run
immediately: `"dummy"` is only 5 characters, so that condition is true and `cdk synth` fails.
Any new validation guard that the current placeholder cannot satisfy will break the CI
dry-run gate.

The advisory AI review workflows run on pull request `opened`, `reopened`, and `synchronize`
events. They require `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` to be configured as GitHub
repository secrets if you want review comments to be posted, but they remain advisory-only and
use `continue-on-error` so review outages do not block merges.

## Required IAM permissions for the deploy role

The IAM role assumed via `AWS_ROLE_TO_ASSUME` must have enough permissions to
deploy both CDK stacks, read S3 data, and fetch CloudWatch Logs for
post-deploy diagnostics.  The CloudWatch Logs permissions are distinct from the
`cloudwatch:GetMetricStatistics` permission already needed for the error-rate
gate.

> **Why `FilterLogEvents` and not `GetLogEvents`?**
> The CI step uses `aws logs filter-log-events` (AWS CLI v1/v2 compatible) rather
> than `aws logs tail` (CLI v2 only).  `filter-log-events` maps to the IAM action
> `logs:FilterLogEvents`; `aws logs tail` maps to `logs:GetLogEvents` +
> `logs:DescribeLogStreams`.  Granting `FilterLogEvents` is sufficient for the
> post-deploy log-dump step; `DescribeLogStreams` is listed below as an optional
> aid for manual troubleshooting.

| Permission | Resource | Why |
| --- | --- | --- |
| `logs:FilterLogEvents` | Log group ARNs for all three Lambdas | Post-deploy log-dump CI step (`aws logs filter-log-events`) — **required** |
| `logs:DescribeLogStreams` | Same log group ARNs | Manual troubleshooting via `aws logs describe-log-streams` — optional but recommended |

The log group ARNs are not fixed strings — they are auto-generated by CDK and
exported as `BackendLambdaLogGroupName`, `PriceRefreshLambdaLogGroupName`, and
`TradingAgentLambdaLogGroupName` in the `BackendLambdaStack` outputs.
Query them after the first deploy:

```bash
aws cloudformation describe-stacks --stack-name BackendLambdaStack \
  --query "Stacks[0].Outputs[?ends_with(OutputKey,'LogGroupName')].[OutputValue]" \
  --output text
```

Minimum inline policy JSON to attach to the deploy role (replace `<region>`,
`<account>`, and the log group name placeholders with values from the outputs above):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBackendLambdaLogRead",
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": [
        "arn:aws:logs:<region>:<account>:log-group:<BackendLambdaLogGroupName>:*",
        "arn:aws:logs:<region>:<account>:log-group:<PriceRefreshLambdaLogGroupName>:*",
        "arn:aws:logs:<region>:<account>:log-group:<TradingAgentLambdaLogGroupName>:*"
      ]
    }
  ]
}
```

Without `logs:FilterLogEvents` the CI step continues silently (it uses
`continue-on-error`) but produces no diagnostic log output.

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

## CDK dry-run CI gate

A lightweight PR-triggered workflow (`.github/workflows/cdk-dry-run.yml`) runs
`cdk synth` for both stacks on every pull request that touches `cdk/**`,
`backend/**`, or `.github/workflows/deploy-lambda.yml`.

**Purpose**: surface synth errors, invalid CDK tokens, and broken asset paths
within ~2 minutes on the PR instead of after a production tag push.

**What it does**:
1. Builds the frontend (`npm run build`) so `frontend/dist` exists — required
   because `StaticSiteStack.BucketDeployment` bundles it as a CDK asset at
   synth time.
2. Runs `npx cdk synth BackendLambdaStack StaticSiteStack -c prod=true` with
   dummy placeholder values for `JWT_SECRET` and `GOOGLE_CLIENT_ID` (the stack
   raises `ValueError` if either is absent, so non-empty placeholders are
   sufficient; no AWS credentials or deploy are performed).
3. Runs `actionlint` on `deploy-lambda.yml` to catch shell/expression mistakes
   in the deploy workflow itself.

**Tagging policy**: do not push a `v*` tag if this job is red on the commit
you intend to tag. A red dry-run means a synth error would abort the production
deploy at the same point.

## CI polling and deploy timeout

When you push a release tag (e.g., `v1.0.0`), the automated deploy workflow (`.github/workflows/deploy-lambda.yml`) waits for the upstream `ci.yml` workflow to complete before proceeding with infrastructure deployment. This is a safety gate to ensure no code is deployed until CI passes.

**The `deploy` job will wait up to 30 minutes (1800 seconds) for the `ci.yml` workflow to complete.** This timeout allows CI pipelines adequate time to finish without blocking indefinitely.

During this wait:
- The workflow polls `ci.yml` status every 30 seconds
- You will see log output like: `ci.yml run <id> for <commit> is still in_progress; waiting 30s...`
- This is expected behavior — **do not cancel the job** during this wait window unless `ci.yml` explicitly fails

**Observable behavior:** If `ci.yml` succeeds within the timeout window, the deploy proceeds immediately. If the timeout fires or `ci.yml` fails, the deploy job exits with an error.

Implementation details are in `.github/workflows/deploy-lambda.yml` (the `check-ci` job), specifically the `timeout_seconds=1800` variable.

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

# Deploy to a live/production environment; retains the Cognito user pool on destroy
./scripts/deploy-to-AWS.ps1 -Backend -DataBucket my-bucket -Prod

# Deploy only the frontend stack
./scripts/deploy-to-AWS.ps1
```

The script changes into the `cdk/` directory, installs the repo-pinned CDK CLI if
necessary, then deploys `BackendLambdaStack` and `StaticSiteStack` when
`-Backend` is specified. Pass `-Prod` for any live environment so the Cognito
user pool uses `RemovalPolicy.RETAIN` and stack deletion does not delete users.

Alternatively, run the commands manually. Deploy the static stack once first so
Cognito exists, pass its outputs into the backend stack, then redeploy the static
stack with the protected API URL in `/config.json`:

```bash
cd cdk
npx cdk bootstrap   # once per account/region
npx cdk deploy StaticSiteStack --require-approval never -c prod=true
UI_AUTH_USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name StaticSiteStack \
  --query "Stacks[0].Outputs[?OutputKey=='UiAuthUserPoolId'].OutputValue" --output text)
UI_AUTH_USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name StaticSiteStack \
  --query "Stacks[0].Outputs[?OutputKey=='UiAuthUserPoolClientId'].OutputValue" --output text)
DATA_BUCKET=my-data-bucket npx cdk deploy BackendLambdaStack --require-approval never \
  --parameters BackendLambdaStack:UiAuthUserPoolId="$UI_AUTH_USER_POOL_ID" \
  --parameters BackendLambdaStack:UiAuthUserPoolClientId="$UI_AUTH_USER_POOL_CLIENT_ID"
BACKEND_URL=$(aws cloudformation describe-stacks --stack-name BackendLambdaStack \
  --query "Stacks[0].Outputs[?OutputKey=='BackendApiUrl'].OutputValue" --output text)
npx cdk deploy StaticSiteStack --require-approval never -c prod=true \
  --parameters StaticSiteStack:BackendApiUrl="$BACKEND_URL"
```

When manually validating drift before a deploy, run `npx cdk diff --all -c prod=true` from
`cdk/`, but do **not** use `npx cdk deploy --all` for a fresh
Cognito-enabled environment. The backend stack needs the user-pool outputs from
the first static deploy, and the static stack needs the backend URL from the
backend deploy, so deployments must follow the static/backend/static sequence
above.

Omit `-c prod=true` only for disposable development stacks where `cdk destroy`
should remove the demo Cognito user pool.

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

1. Re-run `npx cdk diff --all -c prod=true` and confirm intended stack changes are present.
2. Re-run the static/backend/static deployment commands above and capture the
   exact failing resource from CloudFormation events. Do not substitute
   `npx cdk deploy --all` for this flow in a fresh environment because the
   stacks exchange deploy-time parameters between phases.
3. Inspect backend Lambda errors (CloudWatch). Lambda functions in this stack use
   explicit CDK-managed log groups, so read the deployed log group name from the
   stack outputs instead of assuming the `/aws/lambda/<function-name>` convention:

   ```bash
   BACKEND_LOG_GROUP=$(aws cloudformation describe-stacks --stack-name BackendLambdaStack \
     --query "Stacks[0].Outputs[?OutputKey=='BackendLambdaLogGroupName'].OutputValue" --output text)
   # CLI v2: aws logs tail "$BACKEND_LOG_GROUP" --since 30m --follow
   start_ms=$(( ($(date +%s) - 1800) * 1000 ))
   aws logs filter-log-events --log-group-name "$BACKEND_LOG_GROUP" \
     --start-time "$start_ms" --query 'events[].message' --output text
   ```

   The deploy IAM role must have `logs:FilterLogEvents` on the log group ARN for
   the post-deploy log-dump CI step to produce output.

   The scheduled Lambdas expose the same discoverability outputs as
   `PriceRefreshLambdaLogGroupName` and `TradingAgentLambdaLogGroupName`.

4. Validate API Gateway and Cognito API authorization outputs:

   ```bash
   aws cloudformation describe-stacks --stack-name BackendLambdaStack \
     --query "Stacks[0].Outputs[?OutputKey=='BackendApiUrl'].OutputValue" --output text
   aws cloudformation describe-stacks --stack-name StaticSiteStack \
     --query "Stacks[0].Outputs[?starts_with(OutputKey, 'UiAuth')].[OutputKey,OutputValue]" \
     --output table
   curl -i "<BackendApiUrl>/docs"
   ```

   The unauthenticated `curl` should return `401` from API Gateway. Browser users
   must first authenticate through the Cognito hosted UI; the React app then
   forwards the Cognito ID token as `Authorization: Bearer <idToken>` on API calls.

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
