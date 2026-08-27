# Contributor Runbook

This is the opinionated setup path for contributors who want to run AllotMint locally with realistic data, switch between local auth-disabled and auth-enabled flows, run the most relevant tests, and understand the deployment-oriented checks that matter before shipping changes.

For the broader product overview, see [docs/README.md](README.md). For repo-wide agent guidance, see [AGENTS.md](../AGENTS.md).

## 0. Automated code reviews

Before pushing, be aware that pull requests trigger automated AI code reviews via Claude and GPT workflows. These reviews are advisory and posted as PR comments. For details on how these workflows operate, failure handling, and debugging tips, see [docs/AI_REVIEW_WORKFLOWS.md](AI_REVIEW_WORKFLOWS.md).

### CI runs only the areas a PR affects

A PR does not run the whole test suite. The shared reusable workflow
`.github/workflows/_classify-change.yml` runs `scripts/classify_change.py`
once and publishes a flag per area; `ci.yml`, `backend-integration.yml`,
`frontend-tests.yml` and `iac-validation.yml` all gate their jobs on those
same flags, so they cannot disagree about what a PR touched.

| Area | Gated jobs | Triggered by (see `AREA_PATH_RULES`) |
| --- | --- | --- |
| `backend` | `integration-tests`, `lambda-compat`, `python-compatibility`, `validate-backend-deps` | `backend/**`, `tests/**`, `data/**`, `requirements*.txt`, `pyproject.toml`, `pytest.ini`, `mypy.ini`, `config*.yaml`, `scripts/**.py` |
| `frontend` | `frontend-checks`, `frontend-smoke`, `frontend-tests` | `frontend/**`, root `package.json`/`package-lock.json`, `backend/contracts_spa.py` |
| `cdk` | `cdk-tests`, `cdk-validation` | `cdk/**`, `infra/**`, root `package.json`/`package-lock.json` |
| `shell` | `shell-tests` (bats), `lint-shell-scripts` | `**/*.sh`, `scripts/bash/**`, `tests/bash/**`, `Dockerfile*`, `docker/**`, `docker-compose*.yml`, `deploy/**`, `Jenkinsfile*` |

Some checks are deliberately **never** gated, because they are what verifies
the gating: `test` (branch-protection and lockfile validation),
`lint-workflows`, plus `super-linter`, `pr-lint`, `issue-lint` and
`empty-pr-check`.

**The classifier only ever widens.** It is designed so that being wrong costs
wall-clock, never coverage:

- **Doc-only PRs skip every area.** When every changed line is a blank line, a
  full-line comment (`#` in Python; `//`/`/* */` in TS/JS), or content inside a
  `*.md`/`docs/**`/`.github/ISSUE_TEMPLATE/**` file, all area flags are false.
  Any real code line, config file, permission-bit change, or rename touching a
  non-doc path makes the PR non-doc-only.
- **An unrecognised path runs everything.** A file matching no rule in
  `AREA_PATH_RULES` widens to every area, so adding a new top-level directory
  cannot silently skip suites.
- **CI's own machinery runs everything.** Any change under `.github/**`, or to
  `classify_change.py` itself, sets every area — a change to the gating never
  narrows the suite that validates it.
- **Failure runs everything.** A `push` to `main`, a missing base SHA, or a
  classifier crash all classify as "every area affected". Jobs gate on
  `<area> != 'false'` (never `== 'true'`) so empty outputs from a failed
  classifier run the job rather than skipping it.

#### Adding or changing an area

1. Add the path glob to `AREA_PATH_RULES` in `scripts/classify_change.py`.
   Rules are **first-match-wins**, so a narrow rule must precede any broader
   rule it sits inside (`tests/bash/**` before `tests/**`).
2. For a genuinely new area, add it to `AREAS`, declare it as an output in
   `.github/workflows/_classify-change.yml`, and gate the job with
   `if: "!cancelled() && needs.classify-change.outputs.<area> != 'false'"`.
3. If the gated job is a required check, update **both**
   `.github/rulesets/default-branch-protection.json` and
   `EXPECTED_REQUIRED_CHECKS` in
   `scripts/check_branch_protection_required_checks.py` in the same PR. Use the
   job's check-run name (its `name:`, or its job id if it has none) — not the
   `Workflow / Job` label. An admin must then apply the ruleset in the repo's
   GitHub settings; until they do, the daily
   `.github/workflows/branch-protection-drift.yml` run will fail, which is the
   intended reminder.
4. `tests/scripts/test_classify_change.py` and
   `tests/scripts/test_ci_area_gating.py` enforce the mapping and the gating
   invariants; extend them alongside the change.

See [issue #5594](https://github.com/leonarduk/allotmint/issues/5594) for the
original doc-only fast path and
[issue #5722](https://github.com/leonarduk/allotmint/issues/5722) for the
generalisation to per-area gating.

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

- **JWT namespace conflict**: the `jwt` package (v1.x, from PyPI) and `PyJWT` (listed in `requirements.txt` as `pyjwt`) both install into the `jwt` module namespace. If the standalone `jwt` package is present in your environment it will shadow `PyJWT`, causing `AttributeError: module 'jwt' has no attribute 'encode'` in tests. Fix by running `pip uninstall jwt` before `pip install -r requirements.txt`.
- Python formatting/lint configuration lives in `backend/pyproject.toml`, while pytest and coverage defaults live in the root `pyproject.toml`.
- Branch protection required-check policy lives in `docs/BRANCH_PROTECTION.md`. It is validated on every PR by `python scripts/check_branch_protection_required_checks.py` (repo files only) and daily against live GitHub settings by `python scripts/check_live_branch_protection.py`. Required contexts are check-run names (`test`), **not** the `Workflow / Job` labels the Actions UI shows.
- The frontend already has its own `package.json`; use `npm --prefix frontend ...` from the repo root unless you intentionally `cd frontend`.

### Installing the private pro extra

The optional `pro` extra contains the paid screener, risk, compliance,
allowance, and anomaly-repair engine. Its source is the private
`leonarduk/allotmint-pro` repository, so it is deliberately installed over
SSH rather than relying on an HTTPS credential that happens to be cached on a
machine.

1. Ask a repository owner for read access to `leonarduk/allotmint-pro`.
2. [Add an SSH key to your GitHub account](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account).
3. Verify the key and repository access before invoking pip:
   ```bash
   ssh -T git@github.com
   git ls-remote git@github.com:leonarduk/allotmint-pro.git HEAD
   ```
   GitHub's successful `ssh -T` check exits with status 1 because it does not
   provide shell access; the important output is the greeting containing your
   GitHub username. The `git ls-remote` command must print the `HEAD` commit.
4. Install the project and private dependency from the repository root:
   ```bash
   python -m pip install -e ".[pro]"
   ```

If `ssh -T` reports `Permission denied (publickey)`, add or load your GitHub
SSH key before retrying. If the SSH greeting succeeds but `git ls-remote`
reports that the repository was not found, the authenticated GitHub account
does not have access; ask a repository owner to grant it. Do not put a personal
access token in `pyproject.toml`, a shell command, or a committed pip config.

The public application and its normal test suite do not require this extra.
Private-repository CI and deployments run from `allotmint-pro` itself and
check out this public repository, so this local SSH credential is not copied
into public-repository CI.

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
| `HEADLINE_MAX_AGE_HOURS` | Optional | `72` | Sets the maximum age of headlines shown in Market Overview. Read once at startup; a running process must be restarted for a change to take effect. |
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

### Deployment environment variables (required for AWS/GitHub Actions deployment)

Before running the deployment workflow or `pre-deploy-check.sh`, ensure these variables are configured.

**Required for all deployments:**

| Variable | Purpose | Example |
| --- | --- | --- |
| `DATA_BUCKET` | S3 bucket containing account and metadata data | `DATA_BUCKET=allotmint-prod-data` |
| `JWT_SECRET` | Secret key for JWT token signing in the backend API | `JWT_SECRET=<secure-random-string>` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID for frontend/backend authentication | `GOOGLE_CLIENT_ID=...apps.googleusercontent.com` |

**Required when AWS credentials are present (for CDK deployment):**

| Variable | Purpose | Example |
| --- | --- | --- |
| `AWS_REGION` | AWS region for CDK and Lambda deployment | `AWS_REGION=eu-west-2` |
| `GITHUB_DEPLOY_ROLE_ARN` | IAM role ARN that CDK grants permissions to at synthesis time (must match the role that will execute the deploy in GitHub Actions) | `GITHUB_DEPLOY_ROLE_ARN=arn:aws:iam::123456789012:role/github-oidc-deploy-role` |

**⚠️ Important: `GITHUB_DEPLOY_ROLE_ARN` vs. `AWS_ROLE_TO_ASSUME`**

For CI/GitHub Actions deploys:
- `AWS_ROLE_TO_ASSUME`: the GitHub Actions secret that the `configure-aws-credentials` action assumes
- `GITHUB_DEPLOY_ROLE_ARN`: the same ARN, set as an environment variable during CDK synthesis so the stacks grant permissions to the deploy role

For local `cdk deploy` or `pre-deploy-check.sh` runs:
- Export `GITHUB_DEPLOY_ROLE_ARN` to the same value as your deploy role ARN
- This is not needed if you're using GitHub Actions — the workflow maps it for you

**Why both?** `GITHUB_DEPLOY_ROLE_ARN` is read during CDK synthesis (before the deploy even starts) to generate CloudFormation grants. If it's missing at synthesis time, the grants are silently omitted from the template, causing later workflow steps to fail with permission errors.

See `docs/DEPLOY.md` ("Critical: `GITHUB_DEPLOY_ROLE_ARN` environment variable for CDK synth") for detailed background and troubleshooting.

**Optional but recommended:**

| Variable | Purpose | Example |
| --- | --- | --- |
| `SMOKE_TEST_USERNAME` | Username for authenticated smoke test runs | `SMOKE_TEST_USERNAME=test-user@example.com` |
| `SMOKE_TEST_PASSWORD` | Password for authenticated smoke test runs | `SMOKE_TEST_PASSWORD=<secure-password>` |
| `ALLOWED_EMAILS` | Rotates the bootstrap owner allowlist without a code change (see [docs/AUTH.md](AUTH.md#bootstrapping-the-first-owner-account-aws)) | `ALLOWED_EMAILS=owner@example.com` |

**Validating deployment configuration:**

Before deploying, run the deployment environment validator to catch missing configuration early:

```bash
# Check required variables only
bash scripts/bash/validate-deployment-env.sh

# Check required + optional variables
bash scripts/bash/validate-deployment-env.sh --strict
```

Or on Windows:

```powershell
# Check required variables only
pwsh scripts/powershell/validate-deployment-env.ps1

# Check required + optional variables
pwsh scripts/powershell/validate-deployment-env.ps1 -Strict
```

The validator will print clear error messages identifying which variables are missing and why they are needed. All required variables must be present before the deployment workflow can succeed.

**For GitHub Actions deployment:**

Set the above variables as [GitHub repository secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions) or [variables](https://docs.github.com/en/actions/learn-github-actions/variables). Secrets are encrypted and recommended for sensitive values like `JWT_SECRET`.

**For local development and testing:**

Export the variables in your shell or `.env` file before running local deployment commands or pre-deploy checks:

```bash
export DATA_BUCKET=allotmint-dev-data
export JWT_SECRET=dev-secret-key-change-in-production
export GOOGLE_CLIENT_ID=dev-client.apps.googleusercontent.com
```

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
- `./demo-data` is a separate, repo-local dataset meant for local demo walkthroughs and manual UI exploration (`DATA_ROOT=demo-data`). It's intentionally kept apart from `./data`, which several tests read directly (see `tests/conftest.py`'s default `DATA_ROOT` and `tests/test_main.py::test_get_account_demo_fallback`) — don't treat the two as interchangeable, and don't assume trimming one is safe for the other without running the full test suite against the result. `demo-data` currently has two owners (`demo-owner`, `sarah`) with realistic multi-lot holdings across a variety of instrument types; avoid naming a `demo-data` owner literally `demo` — that slug is reserved by `auth.demo_identity` (see below) and gets special-cased out of normal owner listings.
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

### Running multiple local instances side by side

`scripts/bash/run-local-api.sh` and `scripts/run-backend.ps1` pick the first
free port starting at `server.uvicorn_port` (default `8000`) instead of
failing if it's already bound, so a second checkout (e.g. a separate
worktree or clone for a different set of changes) can run its own backend at
the same time. The port actually chosen is logged to the terminal and
written to `.local/ports/backend.port` (gitignored, one per checkout).

`vite.config.ts` reads that file automatically when you start the frontend
dev server (`npm --prefix frontend run dev`, or either `run-frontend`
script) and points `VITE_ALLOTMINT_API_BASE` at the matching backend — the
terminal and browser console both log which backend URL was picked. This
only happens for the dev server; explicitly setting `VITE_ALLOTMINT_API_BASE`
(env var or `.env`) always wins, and production builds/AWS deployments are
unaffected since they don't run the dev server or read `.local/ports/`.

The frontend dev server itself still uses Vite's own default port-clash
handling (`5173`, incrementing if busy) — nothing extra to configure there.

**Scope**: one backend per checkout at a time. `.local/ports/backend.port`
lives at the repo root, so two backends started from the *same* checkout
still race for the same file (last one to finish starting wins) — run
concurrent instances from separate worktrees/clones instead, each with its
own `.local/`.

Set `UVICORN_PORT_FIXED=1` to opt out and require the exact configured
`server.uvicorn_port`, failing loudly instead of shifting to the next free
port (e.g. if you specifically need the default port and want a clash to be
an error rather than silently rebinding elsewhere).

### Minimal local env example

```bash
export DATA_ROOT=./data
export LOCAL_LOGIN_EMAIL=demo@example.com
bash scripts/bash/run-local-api.sh
npm --prefix frontend run dev
```

### Regenerating the docs screenshots

`docs/assets/qa-screenshots/*.png` are captured against this repo's own bundled
demo dataset (`DATA_ROOT=data`), never against a contributor's personal data,
so they're safe to commit to a public repo. To refresh them after a UI
change:

```bash
DATA_ROOT=data bash scripts/bash/run-local-api.sh   # backend, :8000
npm --prefix frontend run dev                        # frontend, :5173
node frontend/scripts/capture-qa-screenshots.mjs
```

The script temporarily flips `config.yaml`'s `reports` tab and
`local_login_email` on to reach pages that need them, then restores the
values it found on disk before it ran. It's not wired into CI — run it
manually and review the diff before committing.

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

### Debugging auth failures

Auth fails at two boundaries; check them in this order:

1. **Gateway authorizer (deployed AWS only).** A request rejected by the API
   Gateway Cognito JWT authorizer (e.g. a `/owners` 401) never reaches the
   Lambda, so it is invisible in the Lambda logs. Open the
   `BackendApiAccessLogGroup` CloudWatch log group, filter by the failing
   `routeKey`, and read `authorizerError` / `status`.
2. **Backend token handling.** As an admin (an email in `ADMIN_EMAILS`), call
   `GET /whoami` with `Authorization: Bearer <token>`. It returns
   `token_present`, the decoded `claims` (`sub`, `email`, `exp`, `iss`,
   `token_use`, `aud`), and `allowed_email_match`. It is admin-gated and never
   echoes the raw token. Note: `/whoami` cannot see gateway rejections — those
   are step 1.

See `docs/AUTH.md` → "Diagnosing auth failures" for full details.

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

## 9. Before pushing a release tag

Run `pre-deploy-check.sh` (or its PowerShell companion) to catch deploy-blocking issues locally before they reach CI:

```bash
bash scripts/bash/pre-deploy-check.sh
```

```powershell
pwsh scripts/powershell/pre-deploy-check.ps1
```

The script runs each check in sequence and prints a `PASS` / `FAIL` / `SKIP` line for each one. It exits non-zero if any check fails. Checks that require AWS credentials (`AWS_ACCESS_KEY_ID`) or CDK environment variables are skipped gracefully with a warning rather than failing.

Checks performed:

1. **Deployment environment variables** — validates that `DATA_BUCKET`, `JWT_SECRET`, and `GOOGLE_CLIENT_ID` are set. If AWS credentials are detected, also validates `AWS_REGION` and `GITHUB_DEPLOY_ROLE_ARN`. See "[Deployment environment variables](#deployment-environment-variables-required-for-awsgithub-actions-deployment)" above for details.
   - `GITHUB_DEPLOY_ROLE_ARN` is required when deploying with AWS credentials because it is read by CDK at synthesis time (not deploy time) to grant the deploy role permission to invoke Lambda functions and call Cognito APIs. If absent during synthesis, those grants are silently omitted and the deploy succeeds but subsequent workflow steps fail. See `docs/DEPLOY.md` ("Critical: `GITHUB_DEPLOY_ROLE_ARN` environment variable for CDK synth") for details.
2. **Dependency dry-run** — pip conflict detection before Docker build.
3. **CDK synth + diff** — confirms the stacks synthesise cleanly and shows what would change (requires `AWS_ACCESS_KEY_ID`, `GITHUB_DEPLOY_ROLE_ARN`, `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `DATA_BUCKET`).
4. **IAM permission simulation** — verifies the deploy role has the S3/Lambda/CloudFormation permissions needed by the deploy workflow (requires AWS credentials and `GITHUB_DEPLOY_ROLE_ARN`).
5. **Backend lint + tests** — `make lint` and `pytest`.
6. **Frontend lint + tests** — `npm --prefix frontend run lint` and Vitest.
7. **CDK tests** — `cdk/tests/` pytest suite.

### What to expect during the automated deploy job

Once you push a release tag (e.g., `v1.0.0`), the `.github/workflows/deploy-lambda.yml` workflow will automatically run. The `check-ci` job waits for the upstream `ci.yml` workflow to complete before proceeding with the actual deployment.

**Important:** The `deploy` job will wait up to **30 minutes (1800 seconds)** for the `ci.yml` workflow to finish. This timeout exists because CI pipelines can take time to run, and we poll rather than immediately fail. During this wait:

- The job polls the CI status every 30 seconds
- You will see messages like `ci.yml run <id> for <commit> is still in_progress; waiting 30s...`
- This is expected behavior — **do not cancel the deploy job** unless CI is explicitly failing (conclusion: `failure` or `cancelled`)

See `.github/workflows/deploy-lambda.yml` (the `check-ci` job) for the implementation details. If CI is expected to take longer than 30 minutes, or if you need to adjust the timeout, refer to the `timeout_seconds` variable in that workflow.

## 10. Deployment-related checks

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

## 11. Quick troubleshooting

- **Frontend cannot reach backend**: set `VITE_ALLOTMINT_API_BASE` explicitly and confirm the backend is listening on the configured host/port.
- **Unexpected demo user or owner**: check `LOCAL_LOGIN_EMAIL`, `DISABLE_AUTH`, `auth.demo_identity`, and `auth.smoke_identity`.
- **Missing data or empty portfolio**: confirm the active `DATA_ROOT` and whether your dataset includes the expected owner under `accounts/`.
- **Unexpected portfolio scope**: the merged portfolio lives at `/`; inspect the
  `owner` and `account` query parameters rather than treating
  `/portfolio/:owner` as a separate page. Legacy owner URLs redirect to the
  equivalent `/?owner=...` scope.
- **Smoke preflight fails**: start the local backend/frontend or set `SMOKE_URL` to a reachable deployment.
- **Google auth errors locally**: verify `GOOGLE_AUTH_ENABLED=true`, `DISABLE_AUTH=false`, and a non-empty `GOOGLE_CLIENT_ID`.
- **Price snapshot absent after deploy (`[WARNING] Price snapshot not yet seeded`)**: the CDK Trigger automatically invokes `PriceRefreshLambda` synchronously during `cdk deploy BackendLambdaStack`, blocking until the snapshot is written. If the warning still appears, the Trigger Lambda likely timed out or the price-refresh Lambda failed. Check `PriceRefreshLambdaLogGroup` in CloudWatch and re-trigger manually: `aws lambda invoke --function-name <PriceRefreshLambda-physical-name> /dev/null`.
- **"Verify price snapshot seeded in S3" deploy step fails with a 403**: this step (`deploy-lambda.yml`) hard-fails the deploy on any `head-object` error other than a missing key (`NoSuchKey`/404, which is a soft pass -- the price-refresh job just hasn't run yet). A 403 means the deploy role genuinely lacks `s3:GetObject`/`s3:ListBucket` on the data bucket, or the bucket policy changed; retrying will not help. Check the CDK grants for `GITHUB_DEPLOY_ROLE_ARN` in `cdk/stacks/backend_lambda_stack.py` (see issue #3191) and re-run once the grant is fixed.

## 12. Canonical command index by task

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

### Pre-deploy checks (run before pushing a release tag)

```bash
bash scripts/bash/pre-deploy-check.sh
```

```powershell
pwsh scripts/powershell/pre-deploy-check.ps1
```

### Deployment-oriented entrypoints

```bash
powershell -ExecutionPolicy Bypass -File scripts/deploy-to-AWS.ps1
npm --prefix frontend run deploy:aws
npm --prefix frontend run deploy:aws:linux
```

## 13. Jenkins mirror of GitHub Actions

The root [`Jenkinsfile`](../Jenkinsfile) mirrors the core GitHub Actions
workflows so the same checks can run on a Jenkins server when GitHub Actions
is unavailable (e.g. quota exhaustion, disabled Actions, or a local CI
requirement). The GitHub workflows remain the source of truth and are not
modified.

### Workflow → Jenkins stage mapping

| GitHub Actions workflow / job | Jenkins stage | Notes |
| --- | --- | --- |
| `ci.yml` `test` | `Repo Hygiene` | Branch-protection, lockfile platform coverage, architecture-diagram checks |
| `ci.yml` `backend-lint` | `Backend Lint` | ruff + black over `backend/` and `tests/`; Jenkins lints the whole tree (non-PR path) |
| `backend-integration.yml` `integration-tests` | `Backend Integration Tests` | Contract sync, mypy, provider parity, full pytest suite with coverage |
| `ci.yml` `lambda-compat` | `Lambda Compat` | Full pytest suite against Lambda-pinned `backend/requirements.txt` in an isolated venv |
| `ci.yml` `validate-backend-deps` | `Validate Backend Deps` | Duplicate-name check, dry-run resolution, root-venv startup import |
| `ci.yml` `python-compatibility` | `Python 3.11 Compat` | Lightweight 3.11 health + parity smoke |
| `ci.yml` `frontend-checks` | `Frontend Checks` | npm lint, `tsc -b` type-check, Vitest run + coverage, npm audit |
| `frontend-tests.yml` `frontend-tests` | `Frontend Checks` | Also runs SPA contract sync and sitemap health check (Python steps) |
| `ci.yml` `frontend-smoke` | `Frontend Smoke` | Optional; enable with `RUN_FRONTEND_SMOKE=true` (downloads Playwright browsers) |
| `ci.yml` `cdk-tests` | `CDK Tests` | `pytest cdk/tests/` against root requirements |
| `iac-validation.yml` `cdk-validation` | `CDK Validation & Dry-Run` | cdk/tests against `cdk/requirements.txt` venv, then `cdk synth` |
| `cdk-dry-run.yml` `cdk-synth` | `CDK Validation & Dry-Run` | prod dry-run synth + `--method=template` guard grep |
| `ci.yml` `shell-tests` | `Shell Tests` | bats tests for deploy shell scripts (AWS CLI calls are mocked) |

### Intentionally not mirrored

These GitHub-only jobs are not mirrored: AI PR-review bots
(`claude-pr-review.yml`, `gpt-pr-review.yml`, `deepseek-pr-review.yml`,
`_ai-pr-review.yml`), `deploy-lambda.yml`, GitHub housekeeping
(`stale.yml`, `label-ai-issues.yml`, `sync-changes-requested-label.yml`,
`dependabot-auto-merge.yml`, `branch-protection-drift.yml`, `empty-pr-check.yml`,
`pr-lint.yml`, `issue-lint.yml`, `conflict-check.yml`, `project-status-in-review.yml`),
`lint-workflows` (actionlint — GitHub workflow YAML linter),
`lint-shell-scripts` (shellcheck — already `continue-on-error` in ci.yml),
Codecov uploads, the private `cicaid` automation tests (token-gated in ci.yml's
`test` job via `CICAID_PRO_TOKEN`; skipped when the secret is absent), and the
optional AWS/S3 data sync (already optional in the workflows; the pytest suite
stubs all AWS interactions).

### Running the pipeline

1. Create a Jenkins pipeline job pointing at this repository with the script
   path `Jenkinsfile`.
2. Set the `GITHUB_TOKEN` credential (GitHub credentials for checkout) and
   ensure the Jenkins server has Docker (pipeline uses `docker.image(...).inside`)
   and network access to npm/pip registries.
3. Set the `BRANCH` parameter (default `*/main`) to the ref you want to build.
4. Optionally enable `RUN_FRONTEND_SMOKE` for the Playwright smoke stage.

Expected run time is long (full backend pytest suite runs in both
`Backend Integration Tests` and `Lambda Compat`, mirroring CI), so set an
adequate job timeout; the pipeline itself allows 180 minutes.
