# AllotMint Repository Guidelines for AI Agents

This repository has a Python/FastAPI backend, a React/Vite frontend, AWS CDK infrastructure, and local/demo data used heavily by tests and smoke checks. If you are taking the project over after time away, read this file first and treat it as the primary operating guide for the whole repo.

## 1. Repo map and mental model

- `backend/`: FastAPI application code, domain services, importers, tasks, and Lambda/local entrypoints.
- `tests/`: primary pytest suite. Prefer adding or updating tests here unless an existing backend-local test sits elsewhere.
- `frontend/`: React + TypeScript SPA built with Vite, plus Vitest and Playwright coverage.
- `data/`: local/demo data used for development and many smoke/test scenarios.
- `scripts/`: local workflow helpers, smoke runners, deployment scripts, and support tooling.
- `cdk/` and `infra/`: AWS infrastructure definitions and deployment assets.
- `docs/`: operational docs, smoke test notes, deployment notes, and user-facing setup details.
- Contributor onboarding runbook: `docs/CONTRIBUTOR_RUNBOOK.md` for the supported local, auth-enabled, test, smoke, and deployment-oriented paths.

## 2. Entrypoints and runtime expectations

### Backend
- App factory: `backend.app:create_app`.
- Local app module used by scripts: `backend.local_api.main:app`.
- Lambda handler path: `backend.lambda_api.handler`.
- Preferred local run path in this repo is the helper script `scripts/bash/run-local-api.sh` or `python -m uvicorn backend.local_api.main:app --reload`.
- Do **not** assume old docs using `uvicorn app:app` are current without verifying the import path first.

### Frontend
- Main boot file: `frontend/src/main.tsx`.
- The SPA expects a backend base URL from `VITE_ALLOTMINT_API_BASE` or falls back to local defaults.
- The frontend has both unit tests (Vitest) and browser smoke coverage (Playwright).

### Smoke / integrated checks
- Repo-level smoke commands live in the root `package.json`.
- Frontend-only smoke commands live in `frontend/package.json`.
- Many smoke flows assume the backend is reachable and may use demo/local identity settings from config or environment variables.

## 3. Canonical commands

### Install
- Backend: `python -m pip install -r requirements.txt -r requirements-dev.txt`
- Frontend: `npm install && npm --prefix frontend install`

### Format and lint
- Python formatting: `make format`
- Python gate: `make lint`
- Frontend lint: `npm --prefix frontend run lint`
- Frontend tests: `npm --prefix frontend run test -- --run` or `npm --prefix frontend run coverage`

### Run locally
- Backend: `bash scripts/bash/run-local-api.sh`
- Frontend: `npm --prefix frontend run dev`

### Smoke checks
- Backend/API smoke: `npm run smoke:test`
- Combined smoke orchestration: `npm run smoke:test:all`
- Frontend smoke: `npm --prefix frontend run smoke:frontend`

## 4. Important repo-specific realities discovered during review

- Python tooling is split across **two config layers**:
  - root `pyproject.toml` is mainly for pytest/coverage and some general settings;
  - `backend/pyproject.toml` is the config actually used by `make format` / `make lint` for Black, isort, and Ruff.
- Root docs may mention Python 3.12, but backend formatting/lint config currently targets Python 3.11. When changing Python-version-sensitive code, verify both the runtime expectation and the active lint config before updating syntax.
- The backend pytest default in the root `pyproject.toml` sets `testpaths = ["tests"]`, so top-level `tests/` is the primary suite.
- The repo already contains `node_modules/` folders. Do not edit vendored/generated dependency trees.
- Many local workflows depend on `data/` fixtures and auth/demo identity fallbacks. Avoid changing default data or auth behavior casually because it can break smoke flows in non-obvious ways.
- There are PowerShell and bash variants of several scripts. Preserve both when changing cross-platform workflows.

## 5. Branch and PR policy

**Never commit directly to `main`.** This applies without exception to all changes: code, documentation, config, and trivial fixes.

Required workflow for every change:
1. Create a branch from `main`
2. Push all changes to that branch
3. Open a PR targeting `main`
4. Wait for review before merging

Branch naming convention: `fix/issue-NNNN-short-description`, `feat/issue-NNNN-short-description`, or `docs/short-description`.

This rule exists to preserve CI gating, review history, and the ability to revert cleanly.

## 6. How to work safely in this codebase

### When modifying backend code
- Keep business logic in domain-oriented modules under `backend/`; avoid pushing logic directly into route handlers when a helper/service module is more appropriate.
- Watch for code paths used by both local FastAPI and Lambda entrypoints.
- Prefer deterministic tests with fixtures under `tests/` or `tests/data/`.
- Be careful with network-dependent integrations (`yfinance`, Google auth, AWS, etc.); add seams/mocks rather than creating tests that require the public internet.

### When modifying frontend code
- Use the existing TypeScript + ESLint + Prettier style in `frontend/`.
- Keep components/pages in the current structure under `frontend/src/` and prefer small, composable changes.
- If you make a perceptible UI change, capture a screenshot when tooling is available.
- Keep API assumptions aligned with backend contracts; if you change payload shapes, update both tests and any dependent UI code.

### When modifying scripts/docs/workflows
- Check whether the same workflow exists in more than one place (`docs/`, `scripts/README.md`, workflow YAML, package scripts, PowerShell helpers).
- Prefer correcting stale instructions instead of adding another conflicting source of truth.
- If you update commands, verify them against the actual package scripts/entrypoints in this repo.

## 7. AI-agent handoff checklist

Before making changes:
1. Read this file.
2. Check `git status` for uncommitted user work and avoid overwriting it.
3. Verify whether there are more specific `AGENTS.md` files deeper in the tree for files you plan to touch.
4. Inspect the command definitions you plan to reference instead of trusting older prose docs.

Before finishing:
1. Run the smallest relevant automated checks.
2. If you changed commands/docs, verify the command names still exist.
3. Update nearby docs when behavior or workflow meaningfully changes.
4. Summarize any environment limitations clearly.

## 8. Commit and PR expectations

- Use focused, imperative commit messages, e.g. `Refresh AI contributor guidance`.
- In PR descriptions, include:
  - what changed,
  - why it changed,
  - what you validated,
  - any known follow-up or risk.
- If you changed UI behavior, attach screenshots.
- If you changed operational workflows, mention the exact commands used for validation.

## 9. Additional AI-facing files in this repo

To support tool-specific agents, keep these files aligned when the repo guidance changes:
- `AGENTS.md` — primary source of truth for agent workflow.
- `CLAUDE.md` — Claude-oriented handoff and operating notes.
- `.github/copilot-instructions.md` — concise GitHub Copilot coding-agent instructions.

When updating one of these, consider whether the same repo facts or command changes should be mirrored in the others.
