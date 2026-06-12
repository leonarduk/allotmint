# Branch protection required checks

The default branch (`main`) must be protected by the repository ruleset stored in
[`.github/rulesets/default-branch-protection.json`](../.github/rulesets/default-branch-protection.json).
That ruleset is the source of truth for deterministic merge gates and should be
kept in sync with GitHub repository settings.

## Required deterministic checks

Require these status checks before a pull request can merge into `main`:

- `CI / test`
- `Backend Integration Tests / integration-tests`
- `Frontend Tests / frontend-tests`
- `PR Body Issue Reference Check / require-issue-reference`
- `Dependency Review / dependency-review`

These names intentionally use the exact `Workflow name / job name` contexts that
GitHub branch protection expects. If a workflow or job is renamed, update the
ruleset and this document in the same pull request.

## Applying the ruleset

Repository administrators can apply the checked-in ruleset with the GitHub CLI.
Create it when it does not exist:

```bash
gh api --method POST repos/leonarduk/allotmint/rulesets \
  --input .github/rulesets/default-branch-protection.json
```

Update it when GitHub already has a ruleset with the same name:

```bash
RULESET_ID=$(gh api repos/leonarduk/allotmint/rulesets \
  --jq '.[] | select(.name == "main deterministic PR gates") | .id')
gh api --method PUT "repos/leonarduk/allotmint/rulesets/${RULESET_ID}" \
  --input .github/rulesets/default-branch-protection.json
```

## Advisory checks

AI review jobs are useful review aids, but they depend on external model
availability and API quotas. Keep these jobs non-blocking and do not add them to
the required-check ruleset:

- `GPT PR Review / GPT AI code review`
- `Claude PR Review / Claude AI code review`

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

This check-run is currently advisory (not in the required-checks list above).
If it is ever added to the ruleset, update this document and the ruleset in
the same pull request.

## CodeQL

CodeQL should be added to the required-check set only after a CodeQL workflow is
configured in this repository and its exact check context is known. Until then,
it is intentionally absent from the ruleset to avoid documenting a required
check that GitHub cannot evaluate.

## Drift detection

`python scripts/check_branch_protection_required_checks.py` verifies that the
ruleset contains exactly the deterministic checks above, that those checks match
current workflow/job names, and that advisory AI review jobs remain non-blocking.
The `CI / test` job runs this script so workflow renames cannot silently weaken
branch protection.
