# Branch protection required checks

The default branch (`main`) is gated by **one** mechanism: the repository
ruleset stored in
[`.github/rulesets/default-branch-protection.json`](../.github/rulesets/default-branch-protection.json).
That file is the source of truth. Classic branch protection must not also set
required status checks — two live mechanisms with two naming conventions is
what caused issue #5728, where the checked-in ruleset enforced nothing at all.

## Context naming — read this before editing the ruleset

A required status check matches a GitHub Actions **check-run name**. That is
**not** the `Workflow / Job` label the Actions UI shows. The rules are:

| Job shape | Check-run name | Example |
|---|---|---|
| job with a `name:` | that `name:` | `CDK infrastructure tests` |
| job without a `name:` | the job id | `test` |
| job delegating via `uses:` | `<caller job id> / <called job name>` | `ai-review / DeepSeek AI code review` |

Getting this wrong does not fail loudly — it leaves every PR pending forever on
a check that never arrives. Verify any new context against a real check run
before adding it:

```bash
gh api "repos/leonarduk/allotmint/commits/<pr-head-sha>/check-runs?per_page=100" --jq '.check_runs[].name'
```

## Required deterministic checks

| Context | Produced by |
|---|---|
| `test` | `ci.yml` job `test` (ungated repo hygiene) |
| `Frontend lint, type-check and unit tests` | `ci.yml` job `frontend-checks` |
| `CDK infrastructure tests` | `ci.yml` job `cdk-tests` |
| `Validate backend/requirements.txt (dry-run)` | `ci.yml` job `validate-backend-deps` |
| `Lambda-compat pytest (backend/requirements.txt)` | `ci.yml` job `lambda-compat` |
| `Frontend smoke tests (preview build)` | `ci.yml` job `frontend-smoke` |
| `integration-tests` | `backend-integration.yml` |
| `require-issue-reference` | `pr-lint.yml` |
| `Check for merge conflicts with main` | `conflict-check.yml` |
| `ai-review / DeepSeek AI code review` | `deepseek-pr-review.yml` via `_ai-pr-review.yml` |

If a workflow or job is renamed, update the ruleset, `EXPECTED_REQUIRED_CHECKS`
in `scripts/check_branch_protection_required_checks.py`, and this document in
the same pull request.

### Skipped jobs count as passing

Every area-gated job above skips on PRs that cannot affect it, and GitHub
reports a skipped job as a *passing* required check. That is only safe because
each gate is written `<area> != 'false'` paired with `!cancelled()`, so a
classifier failure runs the suite rather than skipping it. Do not "simplify"
a gate to `== 'true'` — that turns the gate fail-open. See
`scripts/classify_change.py` and `.github/workflows/_classify-change.yml`.

## Excluded: disabled workflows

`frontend-tests.yml` and `dependency-review.yml` are **disabled** in GitHub
(`gh workflow list --all` reports `disabled_manually`) and were removed from
the required list in #5728. A disabled workflow never reports, so requiring one
blocks every PR permanently. `frontend-tests.yml`'s vitest+coverage run is
already covered by CI's `Frontend lint, type-check and unit tests`.

Re-enabling either one is a deliberate change that must also fix why it was
failing, and must remove the file from `DISABLED_WORKFLOW_FILES` in
`scripts/check_branch_protection_required_checks.py`.

## Review policy

The ruleset requires **0** approving reviews, with no code-owner review, no
stale-review dismissal and no review-thread resolution. This matches what the
repository has actually enforced and is deliberate: a solo-maintained repo
cannot satisfy a 1-approval gate on its own PRs. AI review jobs are advisory
(below); the deterministic checks above are the real gate.

## Applying the ruleset

Requires repo admin — the default `GITHUB_TOKEN` cannot write rulesets, so this
is a human action that CI cannot perform.

```bash
RULESET_ID=$(gh api repos/leonarduk/allotmint/rulesets --jq '.[] | select(.name == "Main") | .id')
gh api --method PUT "repos/leonarduk/allotmint/rulesets/${RULESET_ID}" --input .github/rulesets/default-branch-protection.json
```

Create it if no ruleset with that name exists:

```bash
gh api --method POST repos/leonarduk/allotmint/rulesets --input .github/rulesets/default-branch-protection.json
```

Then, on an open PR, confirm the ruleset is genuinely the gate — the PR's merge
box should list the contexts above as required, and merge should be blocked
while one of them is red. Only once that is confirmed, drop the duplicate
required-checks entry from classic protection (this removes *only* the
required-checks portion; the rest of classic protection is untouched):

```bash
gh api --method DELETE repos/leonarduk/allotmint/branches/main/protection/required_status_checks
```

Do not run that command first. Leaving `main` briefly ungated is worse than the
drift.

## Advisory checks

AI review jobs are useful review aids, but they depend on external model
availability and API quotas. Keep these jobs non-blocking and do not add them to
the required-check ruleset:

- `ai-review / GPT AI code review`
- `ai-review / Claude AI code review`

`ai-review / DeepSeek AI code review` is the deliberate exception and *is*
required.

## Merge conflict check-run

`.github/workflows/conflict-check.yml` produces a check-run named
`"Check for merge conflicts with main"` (the literal value lives in the
workflow's `env.CHECK_RUN_NAME`) from two different triggers:

- `check-merge-conflicts` runs on `pull_request` and reports the result for
  that PR's head SHA directly via the job's own check-run.
- `recheck-open-prs` runs on `push` to `main` and re-validates every open PR
  against the new `main`, posting a fresh check-run under the same name for
  each PR's head SHA via `gh api repos/$REPO/check-runs`.

Both triggers must keep using the exact same check-run name so that GitHub
branch protection's "most recent check-run per name+SHA" evaluation treats
them as the same required check. `recheck-open-prs` always **POSTs** a new
check-run rather than attempting a GET-then-PATCH update: the GitHub Checks
API ties `PATCH /repos/{owner}/{repo}/check-runs/{id}` to the specific
installation token that created the check-run, and the `pull_request` and
`push` triggers receive distinct installation tokens even though both run as
`github-actions[bot]`. A cross-trigger PATCH therefore returns `403`. The
accepted trade-off is that older check-run entries accumulate (cosmetically)
in the "Checks" tab of long-lived PRs; see the inline comments in
`conflict-check.yml` for the full investigation history (issue #3738, PR
#3731).

## CodeQL

CodeQL should be added to the required-check set only after its exact check
context is confirmed against a real check run. Until then, it is intentionally
absent from the ruleset to avoid documenting a required check that GitHub
cannot evaluate.

## Drift detection

Two checkers, because one cannot do both jobs:

| Script | Runs | Sees | Catches |
|---|---|---|---|
| `scripts/check_branch_protection_required_checks.py` | the `test` job, every PR | repo files only | a job renamed out from under a required context; a context pointing at a workflow listed as disabled |
| `scripts/check_live_branch_protection.py` | `branch-protection-drift.yml`, daily | GitHub API (read-only) | the ruleset never being applied, targeting no branches, or having its required checks removed; classic protection re-acquiring required checks; a workflow disabled in the UI |

The live checker needs elevated read access (rulesets are admin-scoped), so it
runs on a schedule with the `BRANCH_PROTECTION_READ_TOKEN` secret — a
fine-grained PAT with read-only **Administration** permission — rather than on
every PR, where a fork PR must never receive a credential. It exits `2` rather
than `0` when it cannot reach the API, so an expired token fails loudly instead
of looking like a clean result.

Run it locally with an admin `gh` login:

```bash
python scripts/check_live_branch_protection.py
```
