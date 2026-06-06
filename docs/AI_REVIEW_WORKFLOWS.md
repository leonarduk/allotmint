# AI Review Workflows

This document describes how the Claude and GPT AI review workflows handle review generation, posting, and failure scenarios.

## Overview

Two GitHub Actions workflows provide automated code reviews on pull requests:

- **claude-pr-review.yml**: Runs Claude AI review via the Anthropic API
- **gpt-pr-review.yml**: Runs GPT review via the OpenAI API

Both workflows follow the same pattern: generate a review, extract a verdict (APPROVE or REQUEST CHANGES), and post the full review to the PR regardless of verdict.

## Verdict Behavior

The verdict extraction step (`extract_verdict.py`) runs the AI review output through a parser that produces one of two results:

1. **APPROVE** — the review found no blocking issues. The step exits 0 and sets `outputs.approved='true'`.
2. **REQUEST CHANGES** — the review flagged issues that should be addressed before merge. The step exits 1 (non-zero) and sets `outputs.approved='false'`.

**Important:** Downstream steps MUST check `steps.check_claude_approval.outputs.approved == 'true'`, NOT the step's exit status or `outcome`. The step is configured with `continue-on-error: true`, so a REQUEST CHANGES verdict (exit 1) does not block subsequent steps — they can run and decide what to do based on the output variable.

Example of correct pattern in a step:
```yaml
- name: Take action based on review
  if: steps.check_claude_approval.outputs.approved == 'true'
  run: echo "PR approved by AI"
```

Example of **incorrect** pattern (will not work as intended):
```yaml
- name: Take action based on review
  if: steps.check_claude_approval.outcome == 'success'  # ❌ Wrong — continues even on REQUEST CHANGES
  run: echo "PR approved by AI"
```

## Review Posting Behavior

### Successful Review

When the AI API successfully generates a review, the full review content is posted to the PR as a comment, including the verdict (APPROVE or REQUEST CHANGES) and detailed reasoning. Users always see the complete rationale for any feedback, enabling them to understand and address concerns.

### Failed Review

If the AI API call fails before producing a non-empty review file (e.g., missing credentials, HTTP error, empty response), a fallback notice is posted instead. The exact text posted is generated in the `else` branch of the `-s` guard in each workflow's "Post review comment" step:

```
## Claude AI Code Review - Failed

The Claude review failed to complete. Check [Actions](<run URL>) for error details.
```

(`<run URL>` is replaced at runtime with the Actions run URL via `$RUN_URL`.) This ensures users are aware that a review was attempted and directs them to the Actions logs for debugging.

### File-Existence Guard

Both workflows use the POSIX test `[ -s /tmp/<reviewer>_review_body.md ]` to distinguish between:

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
- **`continue-on-error: true`**: Set on the "Post review comment" step in both `claude-pr-review.yml` and `gpt-pr-review.yml`. If the `gh pr comment` call fails, the job does not fail. The failure is recorded in the workflow logs but does not block the overall workflow.

## Debugging

When a review fails to post, check the Actions logs for:

1. **API authentication errors**: Verify `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` secrets are configured
2. **Empty responses**: Check the workflow logs for API response status and size; look for `WARNING: ... empty review body`
3. **Network/rate limit errors**: Review the workflow logs for the run; structured logging shows the API status code
4. **GitHub token issues**: Verify `GH_TOKEN` and PR comment posting permissions are correct
5. **PR comment posting failures**: Look for `::warning title=...` annotations in the Actions summary

For more information, see the workflow files in `.github/workflows/`.
