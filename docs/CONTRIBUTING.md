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

## Code quality expectations

AllotMint follows these non-negotiable standards (derived from NASA/JPL Power of Ten):

- **Function length**: Keep functions under ~60 lines. If a function no longer fits on one screen, refactor before making changes.
- **Zero lint warnings**: `make lint` and `npm --prefix frontend run lint` must pass clean. Rewrite code until it passes — do not suppress warnings without documented justification.
- **No silent error swallowing**: Every error path must be explicit. No bare `except: pass`, no `catch` blocks that silently discard errors, no unhandled Promise rejections.
- **Return values checked**: Check return values of functions that can fail. If deliberately discarding one, make it explicit: `_ = function()` in Python or a comment in TypeScript.
- **Minimum scope**: Declare variables as late as possible and as locally as possible. Avoid module-level mutable state.

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

## Git and GitHub workflow

- **Never commit directly to `main`.** Always create a feature branch (`fix/issue-NNNN-...` or `feat/issue-NNNN-...`).
- **Stage files explicitly**: never use `git commit -am` — this can sweep in lock file changes from `npm ci` or `npm install` that strip platform-specific dependencies.
- **Provide issue context**: if implementing a GitHub issue, include `Closes #NNNN` in your PR body so GitHub auto-closes the issue.
- **Wait for review**: all changes require review and CI to pass before merging.

Branch naming convention:
- Bug fixes: `fix/issue-NNNN-short-description`
- Features: `feat/issue-NNNN-short-description`
- Docs/chore: `docs/short-description` or `chore/short-description`

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
