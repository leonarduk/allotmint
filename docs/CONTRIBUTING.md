# Contributing to AllotMint

Thank you for your interest in contributing to AllotMint! This guide will help you get started with development, testing, and deployment workflows.

## Quick start

1. **Read the core guidance**: Start with [AGENTS.md](../AGENTS.md) for detailed repo policies and [CONTRIBUTOR_RUNBOOK.md](CONTRIBUTOR_RUNBOOK.md) for step-by-step setup.
2. **Install dependencies**:
   ```bash
   python -m pip install -r requirements.txt -r requirements-dev.txt
   npm install
   npm --prefix frontend install
   ```
3. **Run locally**: See "Daily local development workflow" in [CONTRIBUTOR_RUNBOOK.md](CONTRIBUTOR_RUNBOOK.md).
4. **Before pushing**: Run `bash scripts/bash/pre-deploy-check.sh` to catch issues early.

## Environment variables for contribution

### Local development

Copy `.env.example` to `.env` and set variables as needed:

| Variable | Required when | Example | What it controls |
| --- | --- | --- | --- |
| `DATA_ROOT` | You want to use local data files | `./data` | Points the backend at a local data directory instead of S3 |
| `LOCAL_LOGIN_EMAIL` | Testing auth-disabled mode | `demo@example.com` | Sets the "logged-in" user when auth is disabled |
| `DISABLE_AUTH` | You want to test without Google Sign-In | `true` | Disables OAuth authentication for quick iteration |
| `APP_ENV` | Switching between environments | `local` | Selects `local`, `production`, or `aws` runtime behavior |
| `GOOGLE_AUTH_ENABLED` | Testing production-like auth | `true` | Enables Google ID-token authentication |
| `GOOGLE_CLIENT_ID` | Using Google auth locally | `your-client.apps.googleusercontent.com` | Google OAuth client for sign-in |
| `VITE_ALLOTMINT_API_BASE` | Backend on a custom port | `http://localhost:8000` | Frontend API endpoint (use when backend isn't on default port) |

### Deployment and testing

For smoke tests, pre-deploy checks, or CI workflows:

| Variable | When needed | Example | Purpose |
| --- | --- | --- | --- |
| `DATA_BUCKET` | Using S3-backed data or testing deploys | `my-data-bucket` | S3 bucket containing account and metadata data |
| `JWT_SECRET` | Pre-deploy checks or deploy workflows | `<random-32-char-secret>` | Secret for JWT token signing |
| `GOOGLE_CLIENT_ID` | Pre-deploy checks or deploy workflows | `client.apps.googleusercontent.com` | OAuth client (same as local auth, used in deployment) |
| `AWS_REGION` | AWS-related operations | `eu-west-2` | AWS region for CDK, Lambda, and CLI operations |
| `GITHUB_DEPLOY_ROLE_ARN` | Local CDK deploy or pre-deploy-check with AWS credentials | `arn:aws:iam::123456789012:role/github-oidc-deploy-role` | IAM role ARN that CDK grants permissions to (read at synthesis time) |
| `AWS_ROLE_TO_ASSUME` | GitHub Actions deploy workflows | `arn:aws:iam::123456789012:role/github-oidc-deploy-role` | Role that GitHub Actions assumes for deployment |

**⚠️ `GITHUB_DEPLOY_ROLE_ARN` vs. `AWS_ROLE_TO_ASSUME`:**

- In CI/GitHub Actions: `AWS_ROLE_TO_ASSUME` is the secret the workflow assumes; the workflow automatically maps it to `GITHUB_DEPLOY_ROLE_ARN` during CDK synthesis.
- Locally: if you have AWS credentials and plan to run `cdk deploy` or `pre-deploy-check.sh`, export `GITHUB_DEPLOY_ROLE_ARN` yourself (it's the same ARN as your deploy role).
- **Why both?** `GITHUB_DEPLOY_ROLE_ARN` is read at CDK synthesis time (before deploy even starts) to generate CloudFormation grants. If missing, those grants are silently omitted.

See `docs/DEPLOY.md` for detailed background and troubleshooting.

## Code quality invariants (non-negotiable)

Derived from the NASA/JPL Power of Ten guidelines — applicable subset only.
C-specific rules (no dynamic allocation, pointer restrictions, preprocessor
limits, recursion ban) are omitted as inapplicable to this stack.

- **Function length**: Keep functions to ~60 lines or fewer — roughly one screen. If a function no longer fits on one screen, refactor before making further changes.
- **Zero lint warnings**: `make lint` and `npm --prefix frontend run lint` must pass clean. If a tool flags something incorrectly, rewrite the code until it doesn't — do not suppress warnings without a documented justification inline.
- **No silent error swallowing**: every error path must be explicitly handled. No bare `except: pass`, no `catch` blocks that discard exceptions silently, no unhandled Promise rejections.
- **No ignored return values**: check return values of functions that can fail. If you deliberately discard a return value, make it explicit (`_ =` in Python, explicit `void` comment in TS) and add a brief comment explaining why.
- **Minimum scope**: declare variables as late as possible and as locally as possible. Avoid module-level mutable state unless genuinely necessary.

## Running tests and validation

### Backend

```bash
# Format and lint
make format
make lint

# Run tests
pytest

# Run a specific test file
pytest tests/<path_to_test>.py

# Validate environment before deploying
bash scripts/bash/validate-deployment-env.sh
```

Some checks depend on live external services and are intentionally excluded
from `pytest`/`make lint` (which must stay hermetic and mock external
integrations — see `CLAUDE.md`). Run these explicitly, and only when you have
the prerequisite installed/authenticated:

```bash
# Smoke-tests scripts/dev_tools/extract_pr_comments.py against a known,
# merged PR. Requires: gh CLI, authenticated, and network access.
make smoke-test-pr-comments
```

### Frontend

```bash
# Lint and type-check
npm --prefix frontend run lint

# Run tests
npm --prefix frontend run test -- --run

# Run coverage
npm --prefix frontend run coverage

# Build (validates bundling)
npm --prefix frontend run build
```

### Pre-deploy validation

Before pushing a release tag or deploying:

```bash
# Single-pass validation (all checks in sequence)
bash scripts/bash/pre-deploy-check.sh

# Windows PowerShell equivalent
pwsh scripts/powershell/pre-deploy-check.ps1
```

This validates environment variables, dependency resolution, CDK synthesis, IAM permissions, linting, and testing in one run.

## Branch and PR policy

**Never commit directly to `main`.** This applies to all changes including
documentation, config, and trivial fixes.

This rule exists to preserve CI gating, review history, and the ability to
revert cleanly. A direct push to `main` bypasses all of these and cannot be
undone without rewriting history.

Treat branch creation as the first implementation step, not something to do
at the end. If the current checkout is dirty or already contains unrelated
work, create a clean worktree from `main` and do the task there.

Always:
1. Create a branch (`fix/issue-NNNN-short-description`, `feat/issue-NNNN-short-description`, `docs/short-description`, or `chore/short-description`)
2. Push changes to the branch
3. Open a PR targeting `main`
4. Wait for review/merge

If implementing a GitHub issue, include an auto-closing reference in the PR
body (for example: `Closes #1234`).

**Stage files explicitly**: never use `git commit -am` — this can sweep in
lock file changes from `npm ci` or `npm install` that strip platform-specific
dependencies.

**Frontend optional dependency handling**: `frontend/package-lock.json` pins
platform-specific optional packages (for example the Linux-only
`@emnapi/core`/`@emnapi/runtime` entries under `@tailwindcss/oxide-wasm32-wasi`,
needed for CI to run `npm ci` on Linux). Regenerating the lock file with
`npm install` on Windows or macOS can silently strip these entries or add
incorrect `peer: true` annotations, which then makes Linux CI fail with
`EUSAGE` even though the change looks unrelated. Before committing any
`frontend/package-lock.json` diff, review it for removed `@emnapi/*` or other
`optionalDependencies`/`peer` entries and restore them if present.

## Automated code reviews

Pull requests trigger automated AI code reviews via Claude and GPT (advisory-only, will not block merges). See [docs/AI_REVIEW_WORKFLOWS.md](AI_REVIEW_WORKFLOWS.md) for details on these workflows and how to debug review failures.

## Accessing help

- For detailed repo policies and agent guidance: see [AGENTS.md](../AGENTS.md)
- For step-by-step local setup and deployment: see [CONTRIBUTOR_RUNBOOK.md](CONTRIBUTOR_RUNBOOK.md)
- For deployment architecture and environment variable deep dives: see [DEPLOY.md](DEPLOY.md)
- For branch protection and required CI checks: see [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md)
- For Python code organization: see `backend/pyproject.toml` and root `pyproject.toml`

## Architecture notes

- **Backend app factory**: `backend.app:create_app`
- **Local backend app**: `backend.local_api.main:app`
- **Frontend entry**: `frontend/src/main.tsx`
- **Primary backend tests**: top-level `tests/`
- **Frontend tests**: `frontend/src/**/*.test.ts(x)`
- **CDK stacks**: `cdk/stacks/` (BackendLambdaStack and StaticSiteStack)

## Common pitfalls to avoid

- **Don't trust stale prose**: verify actual entrypoints and config paths rather than relying on old documentation.
- **Always read full file context**: diff context can hide code that contradicts your intended change.
- **Preserve cross-platform parity**: bash and PowerShell scripts must both work.
- **Be careful around auth toggles and smoke identities**: these often affect local demos and automated flows.
- **Don't edit generated folders**: never manually modify `node_modules/` or vendored code.

## Getting started on your first PR

1. Fork the repository (or create a branch if you have write access).
2. Create a feature branch: `git checkout -b fix/issue-NNNN-description`
3. Install dependencies: `python -m pip install -r requirements.txt -r requirements-dev.txt && npm install && npm --prefix frontend install`
4. Set up a minimal `.env` (or export variables):
   ```bash
   export DATA_ROOT=./data
   export LOCAL_LOGIN_EMAIL=dev@example.com
   export DISABLE_AUTH=true
   ```
5. Start local development:
   ```bash
   # Terminal 1: backend
   bash scripts/bash/run-local-api.sh
   
   # Terminal 2: frontend
   npm --prefix frontend run dev
   ```
6. Make your changes and test them.
7. Run `make lint`, `pytest`, and frontend lint/tests before committing.
8. Commit with a clear message and push to your branch.
9. Open a PR and wait for review.

## Questions?

Open an issue or start a discussion. The project maintainers are here to help!
