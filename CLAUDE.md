# CLAUDE.md

This file gives Claude-style coding agents a fast, practical overview for working effectively in AllotMint. For the full repo policy, read `AGENTS.md` first; this file is the concise companion.

## Quick start

- Language: always respond in English only, never in Chinese or any other language.
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

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md#branch-and-pr-policy) for the
canonical branch/PR rules (never commit to `main`, worktree-first for dirty
checkouts, required PR steps, branch naming, `Closes #NNNN` linking).

## Preferred workflow

0. For any change touching existing files, read the current file content in full from disk before writing; do not rely on diff snippets or memory of earlier reads.
1. Inspect `git status` and avoid disturbing user changes.
2. Create or switch to the task branch before editing files; if the checkout is dirty with unrelated work, create a clean worktree from `main`.
3. Read the exact script/package targets you plan to mention or change.
4. Make the smallest coherent change.
5. Run the narrowest useful validation.
6. Update nearby docs when commands or behavior changed.

## Code quality invariants (non-negotiable)

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md#code-quality-invariants-non-negotiable)
for the canonical rules (function length, zero lint warnings, no silent error
swallowing, no ignored return values, minimum scope).

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
- Check the `resolved` field on each review thread object to determine whether a thread has been addressed. **Note:** `resolved` is only available via GraphQL; the REST API exposes `dismissed` as a proxy. Use `created_at` only as a fallback tiebreaker when `resolved` state is unavailable. A thread created before the latest commit is not necessarily resolved — the reviewer may not have dismissed it yet. Filtering purely on `created_at` silently skips open threads, so prefer the `resolved`/`dismissed` state check first.
- If results look sparse (e.g. only stale comments on old code), treat that as a signal to check the other endpoint before assuming you have the full picture.

### CI / GitHub Actions status
- **`get_pull_request_status` does not cover GitHub Actions.** It calls the legacy Commit Status API and returns `total_count: 0` for repos that use only Actions — which looks like "no CI" but is misleading. Always use `gh run list --repo <owner>/<repo> --branch <head-branch> --limit 10` to get the real Actions run list.
- **Never assume a failing check is a transient API error without reading the log.** Run `gh run view <run-id> --repo <owner>/<repo> --log-failed` for every failing run and read the actual output before drawing any conclusion.
- **The Claude PR Review check exit code is meaningful.** Exit 1 from `extract_verdict.py` means one of two things — distinguish them by reading the log:
  - `✗ Claude review: CHANGES REQUESTED` → the AI produced a real review with blocking feedback; read the review body from the PR's top-level comments and address each finding.
  - `ERROR: Claude review output was empty` → the Anthropic API returned nothing; this is genuinely transient and a re-run is appropriate.
- **Always verify that a green run is on the current HEAD SHA, not a stale commit — and do not declare a PR "ready to merge" until all required checks are green on that SHA.** "Checks re-running" is not the same as "checks passing". A green result on an older SHA does not satisfy the gate. Retrieve the PR head SHA and cross-check it against the run list:
  ```bash
  # Get the PR head SHA
  gh pr view <number> --json headRefOid -q .headRefOid

  # Filter run list to that exact SHA (bash)
  gh run list --repo <owner>/<repo> --branch <branch> --limit 50 \
    --json headSha,status,conclusion,name \
    | jq --arg sha "<head-sha>" '[.[] | select(.headSha == $sha)]'
  ```
  ```powershell
  # PowerShell: use double-quoted "$headSha" so the shell expands the variable before jq sees it
  $headSha = gh pr view <number> --json headRefOid -q .headRefOid
  gh run list --repo <owner>/<repo> --branch <branch> --limit 50 `
    --json headSha,status,conclusion,name `
    | jq --arg sha "$headSha" '[.[] | select(.headSha == $sha)]'
  ```
  If the `jq` filter returns an empty array (`[]`), first verify the branch name is correct, then wait and retry; don't assume "no CI." Concurrent runs on other branches can push your target SHA outside the limit; SHA-matching is the safety net.

### Docs / scripts / workflows
- Look for duplicate instructions in `docs/`, `scripts/README.md`, root scripts, and workflow YAML.
- Prefer consolidating or correcting instructions rather than introducing a new conflicting variant.

### CDK / Infrastructure
- Read the full current file content before editing any CDK stack file; never work from a diff alone.
- CDK high-level grants (`grant_read_write`, `grant_read`, etc.) are broader than their names suggest; verify the full action set in AWS CDK docs and/or synthesized templates before choosing one.
- For IAM/security permission changes, audit the actual handler code by tracing the full call chain and cite specific `file:function` references in comments and PR descriptions as evidence.
- Prefer `bucket.bucket_arn` (bucket-level actions like `s3:ListBucket`) and `bucket.arn_for_objects("*")` (object-level actions like `s3:GetObject`/`s3:PutObject`) over manually constructed `arn:aws:s3:::` strings to stay partition-agnostic; many policies need both.
- CDK tests synthesize CloudFormation templates; verify the synthesized output contains what you expect instead of assuming code and template always align.
