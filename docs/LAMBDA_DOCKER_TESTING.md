# Local Lambda Docker test harness

This harness runs the production Lambda container image locally with the AWS
Lambda Runtime Interface Emulator (RIE), plus DynamoDB Local for handlers that
need a DynamoDB endpoint. It is intended for fast development feedback before a
CDK deploy.

## Runtime parity

The harness builds `backend/Dockerfile.lambda`, the same Dockerfile used by
`BackendLambdaStack`, so it mirrors the production Python Lambda base image
(`public.ecr.aws/lambda/python:3.12`) and handler packaging.

## Quick start

```bash
cp .env.lambda.example .env.lambda
make lambda-test
```

`make lambda-test` builds the Lambda image, starts `lambda-backend` and
`dynamodb-local` from `docker-compose.lambda.yml`, invokes the backend API
handler with `tests/integration/lambda/payloads/http-health-v2.json`, and checks
the response against `tests/integration/lambda/expected/http-health-v2.json`.
The script tears the containers down automatically unless
`KEEP_LAMBDA_TEST_STACK=true` is set.

## Customising the run

All Lambda-specific settings are configurable through `.env.lambda` or shell
environment variables. Do not put real AWS credentials in this file; the default
values are dummy credentials for local-only services.

Useful overrides:

```bash
# Use a specific host Python if python3 is not on PATH.
PYTHON_BIN=python3.11 make lambda-test
```

Useful harness overrides:

```bash
# Keep the stack up after the invocation for manual curl calls.
KEEP_LAMBDA_TEST_STACK=true make lambda-test

# Choose another API Gateway payload/expected pair.
PAYLOAD_FILE=tests/integration/lambda/payloads/http-health-v2.json \
EXPECTED_FILE=tests/integration/lambda/expected/http-health-v2.json \
make lambda-test
```

For handlers with side effects or external dependencies, add a matching expected
response under `tests/integration/lambda/expected/` before wiring them into the
script. The expected response can be a subset of the Lambda response; the script
normalises JSON response bodies before comparing.

## Manual invocation

Start the stack and invoke the RIE endpoint directly:

```bash
docker compose -f docker-compose.lambda.yml --env-file .env.lambda up --build lambda-backend
curl -sS -X POST \
  'http://127.0.0.1:9000/2015-03-31/functions/function/invocations' \
  -H 'Content-Type: application/json' \
  --data-binary @tests/integration/lambda/payloads/http-health-v2.json
```

Enable the optional MailHog container for SES-style SMTP experiments with the
`ses` profile:

```bash
docker compose -f docker-compose.lambda.yml --env-file .env.lambda --profile ses up --build
```
