# AI Review Workflows

This document describes how the Claude, GPT, and DeepSeek AI review workflows handle review generation, posting, and failure scenarios.

## Overview

Three thin caller workflows trigger AI code reviews on pull requests by invoking a shared
reusable workflow:

- **claude-pr-review.yml**: Calls the reusable workflow with the Anthropic provider config
- **gpt-pr-review.yml**: Calls the reusable workflow with the OpenAI provider config
- **deepseek-pr-review.yml**: Calls the reusable workflow with the DeepSeek provider config
- **_ai-pr-review.yml**: Reusable `workflow_call` workflow containing the actual review,
  posting, verdict-checking, and follow-up-issue logic, parameterized per provider

All three providers follow the same pattern: generate a review, extract a verdict (APPROVE or
REQUEST CHANGES), and post the full review to the PR regardless of verdict.

## Onboarding: provisioning API key secrets

Each reviewer requires its provider's API key to be configured as a repository
secret before its workflow can run successfully:

| Reviewer | Secret name | Workflow |
| --- | --- | --- |
| Claude | `ANTHROPIC_API_KEY` | `claude-pr-review.yml` |
| GPT | `OPENAI_API_KEY` | `gpt-pr-review.yml` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-pr-review.yml` |

To provision a key, go to **Settings → Secrets and variables → Actions →
Secrets** and add the relevant `*_API_KEY` secret. `DEEPSEEK_API_KEY` is the
one new contributors most often need to set up first, since DeepSeek is the
only reviewer currently required by branch protection (see
[Why only DeepSeek is required](#why-only-deepseek-is-required)) — obtain the
key from the [DeepSeek platform](https://platform.deepseek.com/api_keys) and
add it under that name.

If a secret is missing, the corresponding reviewer's API call fails and the
workflow posts a failure notice on the PR instead of a review (see
[Failed Review](#failed-review)) rather than silently skipping. A reviewer
can also be disabled outright via its `ENABLE_*_REVIEW` variable — see
[Disabling individual reviewers](#disabling-individual-reviewers) — which
avoids the failure notice entirely when a key won't be provisioned.

## Disabling individual reviewers

Each reviewer can be toggled individually via repository variables.
Set any of these to `false` to disable the corresponding review:

- `ENABLE_CLAUDE_REVIEW` — controls `claude-pr-review.yml`
- `ENABLE_GPT_REVIEW` — controls `gpt-pr-review.yml`
- `ENABLE_DEEPSEEK_REVIEW` — controls `deepseek-pr-review.yml`

When a variable is `false`, the workflow job is skipped (no check-run is created),
and `sync-changes-requested-label.yml` automatically excludes that reviewer
from its conclusion checks. Set these via **Settings → Secrets and variables →
Actions → Variables**. When a variable is absent, the reviewer runs (default `true`).

## Why only DeepSeek is required

`.github/rulesets/default-branch-protection.json` lists `ai-review / DeepSeek
AI code review` as the only AI reviewer in `required_status_checks`. Claude
and GPT are **not** required checks — they still run, still post full
reviews and non-blocking follow-up suggestions on every PR (see
[Review Posting Behavior](#review-posting-behavior)), but a REQUEST CHANGES
verdict from either does not block a merge. This replaced an earlier setup
where Claude and GPT were both required (PR #3279); DeepSeek was added as a
third reviewer and then made the sole required gate in PR #4188.

Rationale:

- **Fewer blocking gates, less flakiness surface.** Each required AI
  reviewer is a blocking dependency on an external LLM API — timeouts, rate
  limits, or transient errors from any *one* of them can stall every PR.
  Requiring only one (with the [timeout/retry handling](#failed-review)
  described above) narrows that surface to a single provider instead of
  three.
- **Redundant review value without redundant blocking.** All three
  reviewers use the same shared prompt (`build_prompt` in
  `review_common.py`) and verdict format, so their blocking value overlaps
  significantly. Keeping Claude and GPT advisory-only preserves their
  review coverage — a human can still read all three opinions — without
  multiplying the failure points that can hold up a merge.
- **DeepSeek was chosen as the sole gate** because it was already running
  successfully across the existing PR set at the time of PR #4188 with no
  reliability concerns distinct from the other two providers.

### Risk of relying on a single required reviewer

Making DeepSeek the only required AI gate concentrates risk: if the
DeepSeek API has an extended outage, changes its response format in a
breaking way, or the `DEEPSEEK_API_KEY` secret is revoked, PRs cannot merge
until the issue is fixed or the reviewer is disabled (via
`ENABLE_DEEPSEEK_REVIEW=false`, which requires updating both the repo
variable **and** `.github/rulesets/default-branch-protection.json`/
`EXPECTED_REQUIRED_CHECKS` in `scripts/check_branch_protection_required_checks.py`
to keep them in sync — see [Adding a new AI reviewer](#adding-a-new-ai-reviewer)
for the equivalent registration steps in reverse).

Mitigations already in place:

- The [retry-with-backoff mechanism](#failed-review) in `fetch_review()`
  absorbs transient DeepSeek API failures (429/5xx, network errors) without
  needing a human to intervene.
- `scripts/check_branch_protection_required_checks.py` runs in CI
  (`.github/workflows/ci.yml`) and fails the build if the ruleset's
  `required_status_checks` entries drift from either the deterministic
  workflow/job names it discovers or the `EXPECTED_REQUIRED_CHECKS` set
  hardcoded in the script — this is what prevents the required-check list
  and the actual workflows from silently diverging (e.g. a reviewer being
  renamed in one place but not the other).
- If DeepSeek needs to be dropped as the required gate entirely, Claude or
  GPT can be promoted to required by adding their check-run context back to
  both `default-branch-protection.json` and `EXPECTED_REQUIRED_CHECKS`,
  since both already run on every PR and their check-run names are stable.

No automated failover between providers exists — promoting a different
reviewer to required is a manual config change, not something the
workflows do automatically.

## Choosing the follow-up issue body provider

When a review APPROVEs and suggests non-blocking follow-ups (see
[Workflow Step Configuration](#workflow-step-configuration)), `create_followup_issues.py`
calls an LLM to expand each suggested title into a full issue body (What/Why/How/
Constraints/LLM tier/Success/Failure). The provider used for this is independent of
which reviewer (Claude/GPT/DeepSeek) approved the PR.

Set the repository variable `FOLLOWUP_LLM_PROVIDER` to one of `claude`, `gpt`, or
`deepseek` to choose the provider. If unset, it defaults to `deepseek`. Set it via
**Settings → Secrets and variables → Actions → Variables**.

Each provider requires its corresponding API key secret to be configured
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `DEEPSEEK_API_KEY`). If the selected
provider's key is missing, the call fails, or `FOLLOWUP_LLM_PROVIDER` names an
unrecognised provider, the issue is created with a minimal fallback body
(`Follow-up suggested by AI review of PR #<n>.`) instead of failing the workflow.

## Verdict Behavior

The verdict extraction step (`extract_verdict.py`) runs the AI review output through a parser that produces one of two results:

1. **APPROVE** — the review found no blocking issues. The step exits 0 and sets `outputs.approved='true'`.
2. **REQUEST CHANGES** — the review flagged issues that should be addressed before merge. The step exits 1 (non-zero) and sets `outputs.approved='false'`.

**Important:** Downstream steps MUST check `steps.check_approval.outputs.approved == 'true'`, NOT the step's exit status or `outcome`. The step is configured with `continue-on-error: true`, so a REQUEST CHANGES verdict (exit 1) does not block subsequent steps — they can run and decide what to do based on the output variable.

Example of correct pattern in a step:
```yaml
- name: Take action based on review
  if: steps.check_approval.outputs.approved == 'true'
  run: echo "PR approved by AI"
```

Example of **incorrect** pattern (will not work as intended):
```yaml
- name: Take action based on review
  if: steps.check_approval.outcome == 'success'  # ❌ Wrong — continues even on REQUEST CHANGES
  run: echo "PR approved by AI"
```

## Review Posting Behavior

### Successful Review

When the AI API successfully generates a review, the full review content is posted to the PR as a comment, including the verdict (APPROVE or REQUEST CHANGES) and detailed reasoning. Users always see the complete rationale for any feedback, enabling them to understand and address concerns.

### Failed Review

If the AI API call fails before producing a non-empty review file (e.g., missing credentials, HTTP error, empty response), a fallback notice is posted instead. The exact text posted is generated in the `else` branch of the `-s` guard in `build_review_comment.sh`, called from the reusable workflow's "Post review comment" step:

```
## Claude AI Code Review - Failed

The Claude review failed to complete. Check [Actions](<run URL>) for error details.
```

(`<run URL>` is replaced at runtime with the Actions run URL via `$RUN_URL`.) This ensures users are aware that a review was attempted and directs them to the Actions logs for debugging.

### File-Existence Guard

The reusable workflow uses the POSIX test `[ -s /tmp/<provider_id>_review_body.md ]` to distinguish between:

1. **File exists and non-empty** (`-s` returns true): API call succeeded → post full review
2. **File missing or empty** (`-s` returns false): API call failed → post fallback notice

This guard is robust to cancellations, timeouts, and partial failures.

## Fallback Mechanisms

### PR Comment

The primary posting mechanism is `gh pr comment`, which posts the review as a comment visible to all PR viewers. If this call fails (e.g., due to GitHub API rate limits or token issues), a warning is logged in the Actions run.

### Step Summary

As a secondary fallback for visibility, the review body is also written to `$GITHUB_STEP_SUMMARY` so it appears in the GitHub Actions run UI. If the `gh pr comment` call fails, the review content is still accessible here.

## Workflow Step Configuration

- **`if: success() || failure()`**: The "Post review comment" step runs even if the verdict is REQUEST CHANGES (which exits the preceding step with a non-zero exit code), so the full review is always visible. The condition excludes cancelled runs to avoid spurious failure notices when a run is superseded by a new push.
- **`continue-on-error: true`**: Set on the "Post review comment" step in `_ai-pr-review.yml`. If the `gh pr comment` call fails, the job does not fail. The failure is recorded in the workflow logs but does not block the overall workflow.
- **`if: steps.check_approval.outputs.approved == 'true'`**: The "Create follow-up issues" step only runs when the review is an APPROVE. On REQUEST CHANGES, no follow-up issues are created — the blocking findings belong in the review itself, not the backlog. This condition is identical for both Claude and GPT. Before this consolidation, GPT created follow-up issues on every verdict; the maintainer confirmed (PR #3933) that the APPROVE-only behavior — Claude's prior behavior — is the intended one for both providers.

## End-to-end validation

PR #3933 itself is the end-to-end validation for this reusable-workflow refactor: every push to that PR triggers both `claude-pr-review.yml` and `gpt-pr-review.yml`, which call `_ai-pr-review.yml` via `workflow_call` with the `anthropic_api_key`/`openai_api_key`/`gh_token` secrets threaded through. Successful runs of `ai-review / Claude AI code review` and `ai-review / GPT AI code review` on that PR (posting review comments, extracting verdicts, and gating follow-up issue creation) confirm the reusable-workflow secret passing and `if:` conditions work as intended.

## Adding a new AI reviewer

The reusable workflow `_ai-pr-review.yml` and the shared `fetch_review()` helper in
`review_common.py` make it possible to add a third reviewer (e.g. Gemini) without copying
the full workflow or HTTP/error-handling scaffolding. The contract:

### 1. Shared prompt and verdict format

Every reviewer must use:

- `build_prompt(pr_title, diff, issue_body)` from `review_common.py` to construct the
  review prompt — this keeps the review dimensions and repo-specific context identical
  across providers.
- The verdict markers `**APPROVE**` / `**REQUEST CHANGES**` at the end of the review, as
  understood by `extract_verdict.py`. Do not introduce new verdict values.

### 2. Review script

Add `.github/scripts/<provider>_review.py` that:

1. Calls `load_review_context(api_key_env)` to read `PR_TITLE`, `DIFF`, `ISSUE_BODY`, and
   the provider's API key from the environment.
2. Returns early via `emit_empty_diff_notice(provider_name)` if the diff is empty.
3. Builds the prompt with `build_prompt(...)`.
4. Calls `fetch_review(url, headers, payload, extractor, provider_label)` from
   `review_common.py`, where `extractor(data) -> (review_text, extra)` parses the
   provider's JSON response. `fetch_review()` handles the HTTP POST, timeout, `HTTPError`
   reporting, and empty-response warning.
5. Calls `finalize_review(review, empty_error_message)` to print the result or fail.

### 3. Output file naming

The reusable workflow writes the review to `/tmp/<provider_id>_review_body.md` and the
posted comment to `/tmp/<provider_id>_comment_body.md`, where `<provider_id>` is the
lowercase identifier passed via the `provider_id` input (e.g. `claude`, `gpt`, `gemini`).

### 4. Registering the provider

Add a new thin caller workflow, e.g. `.github/workflows/gemini-pr-review.yml`:

```yaml
name: Gemini PR Review

on:
  pull_request:
    types: [opened, reopened, synchronize]

jobs:
  ai-review:
    if: ${{ github.actor != 'dependabot[bot]' }}
    permissions:
      pull-requests: write
      contents: read
      issues: write
    uses: ./.github/workflows/_ai-pr-review.yml
    with:
      provider_name: Gemini
      provider_id: gemini
      review_script: .github/scripts/gemini_review.py
      workflow_file: gemini-pr-review.yml
    secrets:
      anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
      gh_token: ${{ secrets.GITHUB_TOKEN }}
```

`anthropic_api_key` and `gh_token` are required by the reusable workflow regardless of
provider: `gh_token` is used for `gh` CLI calls, and `anthropic_api_key` (along with the
optional `openai_api_key`/`deepseek_api_key`) is threaded through to follow-up issue
creation (`create_followup_issues.py`) on every reviewer's APPROVE verdict — see
[Choosing the follow-up issue body provider](#choosing-the-follow-up-issue-body-provider).
Pass any provider-specific secret (e.g. a `GEMINI_API_KEY`) by adding
a new optional secret to `_ai-pr-review.yml` and threading it through to the "Call API"
step's `env:` block, following the existing `openai_api_key` pattern.

## 'Changes Requested' label contract

`claude-pr-review.yml`, `gpt-pr-review.yml`, and `deepseek-pr-review.yml` each add the `Changes
Requested` label to a PR when their own verdict is REQUEST CHANGES (see
[Verdict Behavior](#verdict-behavior) above). Removing the label is handled
separately by `.github/workflows/sync-changes-requested-label.yml`, which is
triggered via `workflow_run` after any review workflow completes.

The contract: the label is removed **only when all enabled** reviewers (see
[Disabling individual reviewers](#disabling-individual-reviewers)) have
concluded with `success` for the current head SHA. Disabled reviewers are
automatically excluded from the check. This cannot be done from inside any
single review job, because a job's own check-run conclusion isn't finalized
until the job completes — so no workflow can observe the other reviewers'
conclusions in time when all run concurrently on the same push.

When the label is removed, `sync-changes-requested-label.yml` also posts a
PR comment confirming all enabled AI reviews passed. If the label was not present
(e.g. all reviews approved on the first pass), no comment is posted.

### Stuck-label fallback

The `workflow_run` trigger can miss a PR — e.g. the triggering review run is
cancelled by a superseding push before its `completed` event fires, or the
webhook delivery is dropped — leaving the label "stuck" even though the
latest commit's reviews all later succeeded. To recover from this,
`sync-changes-requested-label.yml` also runs on a `schedule` (every 30
minutes) and via `workflow_dispatch` (for manual triggering). The scheduled
run lists every open PR that still carries the `Changes Requested` label and
re-runs the same reconciliation logic (shared via
`.github/scripts/reconcile_changes_requested_label.sh`) against each one, so
a PR whose reviews have actually passed gets its label cleared within the
next scheduled sweep even if the triggering event was lost.

`workflow_dispatch` also accepts an optional `pr_number` input to
force-reconcile a single PR immediately, instead of waiting for the next
scheduled sweep or scanning every open PR. Run it from the Actions tab (or
`gh workflow run sync-changes-requested-label.yml -f pr_number=123`) when a
specific PR's label is stuck. Leaving `pr_number` empty falls back to the
full sweep, same as before.

If a fourth reviewer is added (see [Adding a new AI reviewer](#adding-a-new-ai-reviewer)),
update `sync-changes-requested-label.yml`'s `workflows:` trigger list and its
conclusion checks to include the new provider's check-run name — otherwise
the label will never be removed once the new reviewer also requests changes.

## Debugging

When a review fails to post, check the Actions logs for:

1. **API authentication errors**: Verify `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` secrets are configured
2. **Empty responses**: Check the workflow logs for API response status and size; look for `WARNING: ... empty review body`
3. **Network/rate limit errors**: Review the workflow logs for the run; structured logging shows the API status code
4. **GitHub token issues**: Verify `GH_TOKEN` and PR comment posting permissions are correct
5. **PR comment posting failures**: Look for `::warning title=...` annotations in the Actions summary

For more information, see the workflow files in `.github/workflows/`.
