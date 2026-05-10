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
