# CLAUDE.md

This file gives Claude-style coding agents a fast, practical overview for working effectively in AllotMint. For the full repo policy, read `AGENTS.md` first; this file is the concise companion.

## Quick start

- Root guide of record: `AGENTS.md`
- Contributor onboarding/run modes: `docs/CONTRIBUTOR_RUNBOOK.md`
- Backend app factory: `backend.app:create_app`
- Local backend app: `backend.local_api.main:app`
- Frontend app entry: `frontend/src/main.tsx`
- Primary backend tests: top-level `tests/`

## Most useful commands

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
make format
make lint
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
bash scripts/bash/run-local-api.sh
npm --prefix frontend run dev
npm run smoke:test
npm run smoke:test:all
npm run smoke:test:codex:poc
```

## High-signal warnings

- Do not trust stale prose that references `uvicorn app:app`; verify actual backend entrypoints first.
- Before pushing any fix, read the full current content of every file you plan to change. Diff context is not a substitute for full-file context and can hide code that directly contradicts your intended fix.
- Python config is split: root `pyproject.toml` handles pytest/coverage, while `backend/pyproject.toml` drives Black/isort/Ruff for the backend.
- Backend lint/format config currently targets Python 3.11 semantics even though some docs mention Python 3.12.
- Avoid editing generated or vendored folders like `node_modules/`.
- Never use `git commit -am`; always stage specific files explicitly. The `-a` flag will sweep in any lock file changes from local `npm ci` or `npm install` runs, which can strip platform-specific optional deps (e.g. Linux `@emnapi` entries) and break CI.
- Be cautious around `data/`, auth toggles, and smoke-test identities; these often affect local demos and automated flows.
- Preserve cross-platform workflow parity when touching scripts because the repo uses both bash and PowerShell helpers.

## Branch and PR policy

**Never commit directly to `main`.** This applies to all changes including documentation, config, and trivial fixes.

This rule exists to preserve CI gating, review history, and the ability to revert cleanly.
A direct push to `main` bypasses all of these and cannot be undone without rewriting history.

Treat branch creation as the first implementation step. Before editing files, create or switch to a non-`main` branch. If the current checkout is dirty or already contains unrelated work, create a clean worktree from `main` and do the task there.

Always:
1. Create a branch (`git checkout -b <branch-name>` or via API)
2. Push changes to the branch
3. Open a PR targeting `main`
4. Wait for review/merge
5. If implementing a GitHub issue, include an auto-closing reference in the PR body (for example: `Closes #1234`).

Branch naming convention: `fix/issue-NNNN-short-description` or `feat/issue-NNNN-short-description` or `docs/short-description`.

## Preferred workflow

0. For any change touching existing files, read the current file content in full from disk before writing; do not rely on diff snippets or memory of earlier reads.
1. Inspect `git status` and avoid disturbing user changes.
2. Create or switch to the task branch before editing files; if the checkout is dirty with unrelated work, create a clean worktree from `main`.
3. Read the exact script/package targets you plan to mention or change.
4. Make the smallest coherent change.
5. Run the narrowest useful validation.
6. Update nearby docs when commands or behavior changed.

## Code quality invariants (non-negotiable)

Derived from the NASA/JPL Power of Ten guidelines — applicable subset only.
C-specific rules (no dynamic allocation, pointer restrictions, preprocessor limits, recursion ban) are omitted as inapplicable to this stack.

- **Function length**: keep functions to ~60 lines or fewer. If a function no longer fits on one screen, refactor before making further changes.
- **Zero lint warnings**: `make lint` and `npm --prefix frontend run lint` must pass clean. If a tool flags something incorrectly, rewrite the code until it doesn't — do not suppress warnings without a documented justification inline.
- **No silent error swallowing**: every error path must be explicitly handled. No bare `except: pass`, no `catch` blocks that discard exceptions silently, no unhandled Promise rejections.
- **No ignored return values**: check return values of functions that can fail. If you deliberately discard a return value, make it explicit (`_ =` in Python, explicit `void` comment in TS) and add a brief comment explaining why.
- **Minimum scope**: declare variables as late as possible and as locally as possible. Avoid module-level mutable state unless genuinely necessary.

## If you touch specific areas

### Backend
- Keep domain logic out of routes when possible.
- Add/update pytest coverage under `tests/`.
- Mock external integrations instead of depending on live network access.

### Frontend
- Follow existing TypeScript/ESLint/Prettier conventions.
- Add/update Vitest coverage for logic changes.
- Capture screenshots for visible UI changes when tooling allows.

### GitHub PRs
- When reviewing PR comments, always call **both** `get_pull_request_comments` (inline review thread comments) and the issue comments endpoint (top-level PR conversation comments) in parallel — they cover different things and GitHub exposes them via separate APIs.
- Filter comments by `created_at` vs the last commit timestamp so already-addressed threads are not re-processed.
- If results look sparse (e.g. only stale comments on old code), treat that as a signal to check the other endpoint before assuming you have the full picture.

### CI / GitHub Actions status
- **`get_pull_request_status` does not cover GitHub Actions.** It calls the legacy Commit Status API and returns `total_count: 0` for repos that use only Actions — which looks like "no CI" but is misleading. Always use `gh run list --repo <owner>/<repo> --branch <head-branch> --limit 10` to get the real Actions run list.
- **Never assume a failing check is a transient API error without reading the log.** Run `gh run view <run-id> --repo <owner>/<repo> --log-failed` for every failing run and read the actual output before drawing any conclusion.
- **The Claude PR Review check exit code is meaningful.** Exit 1 from `extract_verdict.py` means one of two things — distinguish them by reading the log:
  - `✗ Claude review: CHANGES REQUESTED` → the AI produced a real review with blocking feedback; read the review body from the PR's top-level comments and address each finding.
  - `ERROR: Claude review output was empty` → the Anthropic API returned nothing; this is genuinely transient and a re-run is appropriate.
- **Do not declare a PR "ready to merge" until `gh run list` shows all required checks green on the current HEAD SHA.** "Checks re-running" is not the same as "checks passing".

### Docs / scripts / workflows
- Look for duplicate instructions in `docs/`, `scripts/README.md`, root scripts, and workflow YAML.
- Prefer consolidating or correcting instructions rather than introducing a new conflicting variant.

### CDK / Infrastructure
- Read the full current file content before editing any CDK stack file; never work from a diff alone.
- CDK high-level grants (`grant_read_write`, `grant_read`, etc.) are broader than their names suggest; verify the full action set in AWS CDK docs and/or synthesized templates before choosing one.
- For IAM/security permission changes, audit the actual handler code by tracing the full call chain and cite specific `file:function` references in comments and PR descriptions as evidence.
- Prefer `bucket.bucket_arn` (bucket-level actions like `s3:ListBucket`) and `bucket.arn_for_objects("*")` (object-level actions like `s3:GetObject`/`s3:PutObject`) over manually constructed `arn:aws:s3:::` strings to stay partition-agnostic; many policies need both.
- CDK tests synthesize CloudFormation templates; verify the synthesized output contains what you expect instead of assuming code and template always align.
