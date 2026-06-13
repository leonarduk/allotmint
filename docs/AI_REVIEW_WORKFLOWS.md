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
provider: `anthropic_api_key` is used for follow-up issue creation
(`create_followup_issues.py`) on every reviewer's APPROVE verdict, and `gh_token` is used
for `gh` CLI calls. Pass any provider-specific secret (e.g. a `GEMINI_API_KEY`) by adding
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
