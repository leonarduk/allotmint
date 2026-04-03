# Contributor Runbook

This is the opinionated setup path for contributors who want to run AllotMint locally with realistic data, switch between local auth-disabled and auth-enabled flows, run the most relevant tests, and understand the deployment-oriented checks that matter before shipping changes.

For the broader product overview, see [docs/README.md](README.md). For repo-wide agent guidance, see [AGENTS.md](../AGENTS.md).

## 1. Supported run modes at a glance

| Mode | When to use it | Backend entrypoint | Frontend entrypoint | Auth expectation | Data expectation |
| --- | --- | --- | --- | --- | --- |
| Local API + frontend | Daily development against local/demo data | `bash scripts/bash/run-local-api.sh` | `npm --prefix frontend run dev` | Usually disabled via `auth.disable_auth: true` | Local `data/` or configured `DATA_ROOT` |
| Local auth-enabled | Verify Google sign-in and protected routes before deploy | `bash scripts/bash/run-local-api.sh` with auth env/config set | `npm --prefix frontend run dev` | Enabled | Local data plus Google OAuth configuration |
| Test mode | Fast automated validation while editing | `pytest` / frontend Vitest | n/a | Usually mocked or disabled in tests | Fixtures under `tests/` and sample repo data |
| Smoke mode | End-to-end checks against a running stack | Existing backend/frontend deployment or local stack | Existing backend/frontend deployment or local stack | Optional token depending on target | Uses configured smoke identity and available account data |
| AWS / deployment checks | Validate packaging and deploy-specific assumptions | CDK/deploy scripts | frontend build/deploy scripts | Enabled in production-style environments | S3-backed data and deployment env vars |

## 2. Install dependencies

From the repository root:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
```

Notes:

- Python formatting/lint configuration lives in `backend/pyproject.toml`, while pytest and coverage defaults live in the root `pyproject.toml`.
- The frontend already has its own `package.json`; use `npm --prefix frontend ...` from the repo root unless you intentionally `cd frontend`.

## 3. Environment variables you are most likely to need

Copy `.env.example` to `.env` if you want a local file-backed setup, or export the variables directly in your shell.

### Core local/runtime variables

| Variable | Required when | Example | What it controls |
| --- | --- | --- | --- |
| `DATA_ROOT` | Optional for local runs | `DATA_ROOT=./data` | Overrides the configured application data root. |
| `LOCAL_LOGIN_EMAIL` | Optional for auth-disabled local UX | `LOCAL_LOGIN_EMAIL=demo@example.com` | Makes the UI/backend behave like a specific local user while auth stays disabled. |
| `DISABLE_AUTH` | Optional override | `DISABLE_AUTH=true` | Overrides `auth.disable_auth` from `config.yaml`. |
| `APP_ENV` | Optional override | `APP_ENV=local` | Selects `local`, `production`, or `aws` runtime behavior. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional | `123456:token` / `123456789` | Enables Telegram alert forwarding. |
| `ALPHA_VANTAGE_KEY` | Optional unless using Alpha Vantage-backed features | `demo` | Enables Alpha Vantage integrations without storing the secret in git. |
| `TIMESERIES_CACHE_BASE` | Optional | `TIMESERIES_CACHE_BASE=./data/timeseries` | Overrides the configured timeseries cache directory. |

### Local auth-enabled mode

| Variable | Required when | Example | What it controls |
| --- | --- | --- | --- |
| `GOOGLE_AUTH_ENABLED` | Required to enable Google auth via env | `GOOGLE_AUTH_ENABLED=true` | Enables Google ID-token based authentication. |
| `GOOGLE_CLIENT_ID` | Required when Google auth is enabled | `GOOGLE_CLIENT_ID=...apps.googleusercontent.com` | Google OAuth client used by backend and frontend config. |
| `ALLOWED_EMAILS` | Recommended when auth is enabled | `ALLOWED_EMAILS=user@example.com,admin@example.com` | Restricts login to specific email addresses. |

### Smoke mode variables

| Variable | Required when | Example | What it controls |
| --- | --- | --- | --- |
| `SMOKE_URL` | Recommended for non-default targets | `SMOKE_URL=https://example.com` | Base URL used by backend and frontend smoke suites. |
| `TEST_ID_TOKEN` | Optional, but required for protected targets | `TEST_ID_TOKEN=<jwt-or-id-token>` | Bearer token used by backend smoke requests. |
| `SMOKE_AUTH_TOKEN` | Optional | `SMOKE_AUTH_TOKEN=<access-token>` | Stored in frontend local storage for authenticated smoke checks. |
| `SMOKE_IDENTITY` | Optional | `SMOKE_IDENTITY=demo` | Overrides the configured smoke owner/slug used by backend smoke requests. |

### AWS / deployment-oriented variables

| Variable | Required when | Example | What it controls |
| --- | --- | --- | --- |
| `DATA_BUCKET` | Required for AWS-backed data loading | `DATA_BUCKET=allotmint-prod-data` | S3 bucket for account and metadata data in AWS mode. |
| `SNS_TOPIC_ARN` | Optional | `arn:aws:sns:us-east-1:123456789012:allotmint` | Publishes alerts to SNS. |
| `ALERT_THRESHOLDS_URI` | Optional | `s3://bucket/alert-thresholds.json` | Storage backend for alert thresholds. |
| `PUSH_SUBSCRIPTIONS_URI` | Optional | `ssm://allotmint/push-subscriptions` | Storage backend for push subscriptions. |
| `S3_BUCKET` / `CLOUDFRONT_DISTRIBUTION_ID` | Required by frontend AWS deploy scripts | `S3_BUCKET=app-bucket` | Frontend deployment destination and cache invalidation target. |
| `AWS_REGION` | Common for deploy scripts | `AWS_REGION=eu-west-2` | Region used by AWS CLI/CDK/frontend deploy helpers. |
| `CDK_PYTHON` | Optional | `CDK_PYTHON=.venv/bin/python` | Forces a specific Python interpreter for CDK workflows. |

### Frontend-specific variables

| Variable | Required when | Example | What it controls |
| --- | --- | --- | --- |
| `VITE_ALLOTMINT_API_BASE` | Required when the backend is not at `http://localhost:8000` | `VITE_ALLOTMINT_API_BASE=http://localhost:8000` | Base URL for frontend API requests. |
| `VITE_API_URL` | Optional fallback | `VITE_API_URL=https://api.example.com` | Secondary frontend API base fallback. |
| `VITE_APP_BASE_URL` | Optional for build/deploy flows | `VITE_APP_BASE_URL=https://app.example.com` | Used by frontend build/deploy tooling. |
| `VITE_API_TOKEN` | Optional | `VITE_API_TOKEN=<token>` | Build/runtime token consumed by frontend workflows that expect it. |

## 4. Data directory expectations and caveats

AllotMint depends heavily on realistic local/demo data.

- `config.yaml` currently points `paths.data_root` at `../allotmint-data`, not the repository-local `./data` directory.
- `DATA_ROOT` overrides that config and is the safest way to point the app at a different dataset for local work.
- The backend resolves account data relative to the active data root, typically under `accounts/`.
- Many tests and smoke flows assume that representative data exists under `data/accounts/` or the configured equivalent.
- Local page-cache files are written under `data/cache/` (or the active data root equivalent).
- The local startup script will try to sync data from S3 when `DATA_BUCKET` is set; otherwise it skips the sync.

### Practical guidance

- If you already have the companion data repo or a synced local dataset, set `DATA_ROOT` to that location before starting the backend.
- If you want repo-local demo data for quick experiments, ensure the needed files exist under `./data` and export `DATA_ROOT=./data`.
- Do not casually rename or remove demo owners referenced by `auth.demo_identity`, `auth.smoke_identity`, tests, or smoke scripts.
- When auth is disabled, `auth.demo_identity` and `LOCAL_LOGIN_EMAIL` determine what the app treats as the active user.

## 5. Daily local development workflow

### Recommended local API + frontend flow

1. Install dependencies.
2. Decide which dataset you want to use and export `DATA_ROOT` if needed.
3. Start the backend:

   ```bash
   bash scripts/bash/run-local-api.sh
   ```

4. Start the frontend in a second shell:

   ```bash
   npm --prefix frontend run dev
   ```

5. Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

This path is preferred over outdated docs that still mention `uvicorn app:app`.

### Minimal local env example

```bash
export DATA_ROOT=./data
export LOCAL_LOGIN_EMAIL=demo@example.com
bash scripts/bash/run-local-api.sh
npm --prefix frontend run dev
```

## 6. Local auth-enabled mode

Use this when you need to verify sign-in, protected routes, or production-like auth assumptions.

1. Configure Google auth values:

   ```bash
   export GOOGLE_AUTH_ENABLED=true
   export GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   export ALLOWED_EMAILS=you@example.com
   ```

2. Ensure auth is not disabled:

   ```bash
   export DISABLE_AUTH=false
   ```

3. Start the backend and frontend with the same commands as local development.
4. Confirm the frontend points at the correct backend, especially if you are not using the default localhost port:

   ```bash
   export VITE_ALLOTMINT_API_BASE=http://localhost:8000
   npm --prefix frontend run dev
   ```

### Caveats for auth-enabled local mode

- `GOOGLE_CLIENT_ID` is effectively required whenever `GOOGLE_AUTH_ENABLED=true`.
- If `DISABLE_AUTH` remains true, the app will continue to use demo/local identity behavior instead of enforcing auth.
- `ALLOWED_EMAILS` is not strictly mandatory, but without it you may get broader login access than intended.
- Smoke and test flows may still use mock or token-driven auth instead of interactive Google sign-in.

## 7. Test mode

Use the smallest validation that matches your change.

### Backend-focused

```bash
pytest
```

For a narrower run while iterating:

```bash
pytest tests/<path_to_test>.py
```

### Frontend-focused

```bash
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
```

### Python formatting and lint

```bash
make format
make lint
```

## 8. Smoke mode

Smoke mode assumes there is already a reachable backend and, for combined checks, a reachable frontend.

### Run backend smoke checks only

```bash
npm run smoke:test
```

### Run backend + frontend smoke orchestration

```bash
npm run smoke:test:all
```

### Run frontend smoke only

```bash
npm --prefix frontend run smoke:frontend
```

### Examples

Against the default local stack:

```bash
npm run smoke:test
npm run smoke:test:all
```

Against a deployed target:

```bash
SMOKE_URL=https://example.com npm run smoke:test:all
SMOKE_URL=https://example.com TEST_ID_TOKEN=token npm run smoke:test
SMOKE_URL=https://example.com npm --prefix frontend run smoke:frontend
```

### Smoke-mode caveats

- Backend smoke checks default to `http://localhost:8000` when `SMOKE_URL` is unset.
- Frontend smoke checks default to `http://localhost:5173` when `SMOKE_URL` is unset.
- Protected environments need `TEST_ID_TOKEN` and sometimes `SMOKE_AUTH_TOKEN`.
- The smoke owner defaults to `auth.smoke_identity` from `config.yaml` unless you export `SMOKE_IDENTITY`.

## 9. Deployment-related checks

Before or alongside deployment work, group checks by task.

### Validate Python/backend changes

```bash
make lint
pytest
```

### Validate frontend changes

```bash
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
npm --prefix frontend run build
```

### Validate smoke coverage expectations

```bash
npm run smoke:test
npm run smoke:test:all
```

### AWS / deploy helpers

```bash
powershell -ExecutionPolicy Bypass -File scripts/deploy-to-AWS.ps1
npm --prefix frontend run deploy:aws
npm --prefix frontend run deploy:aws:linux
```

Only run the deploy commands when you intentionally want to deploy; they are listed here so contributors know the canonical entrypoints.

## 10. Quick troubleshooting

- **Frontend cannot reach backend**: set `VITE_ALLOTMINT_API_BASE` explicitly and confirm the backend is listening on the configured host/port.
- **Unexpected demo user or owner**: check `LOCAL_LOGIN_EMAIL`, `DISABLE_AUTH`, `auth.demo_identity`, and `auth.smoke_identity`.
- **Missing data or empty portfolio**: confirm the active `DATA_ROOT` and whether your dataset includes the expected owner under `accounts/`.
- **Smoke preflight fails**: start the local backend/frontend or set `SMOKE_URL` to a reachable deployment.
- **Google auth errors locally**: verify `GOOGLE_AUTH_ENABLED=true`, `DISABLE_AUTH=false`, and a non-empty `GOOGLE_CLIENT_ID`.

## 11. Canonical command index by task

### Install

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
```

### Run locally

```bash
bash scripts/bash/run-local-api.sh
npm --prefix frontend run dev
```

### Format and lint

```bash
make format
make lint
npm --prefix frontend run lint
```

### Tests

```bash
pytest
npm --prefix frontend run test -- --run
npm --prefix frontend run coverage
```

### Smoke

```bash
npm run smoke:test
npm run smoke:test:all
npm --prefix frontend run smoke:frontend
```

### Codex browser-testing proof of concept

```bash
npm run smoke:test:codex:poc
```

For setup and exploratory Codex+MCP usage, see [docs/CODEX_PLAYWRIGHT_MCP.md](CODEX_PLAYWRIGHT_MCP.md).

### Deployment-oriented entrypoints

```bash
powershell -ExecutionPolicy Bypass -File scripts/deploy-to-AWS.ps1
npm --prefix frontend run deploy:aws
npm --prefix frontend run deploy:aws:linux
```
