# AI Review Workflows

This document describes how the Claude and GPT AI review workflows handle review generation, posting, and failure scenarios.

## Overview

Two GitHub Actions workflows provide automated code reviews on pull requests:

- **claude-pr-review.yml**: Runs Claude AI review via the Anthropic API
- **gpt-pr-review.yml**: Runs GPT review via the OpenAI API

Both workflows follow the same pattern: generate a review, extract a verdict (APPROVE or REQUEST CHANGES), and post the full review to the PR regardless of verdict.

## Review Posting Behavior

### Successful Review

When the AI API successfully generates a review, the full review content is posted to the PR as a comment, including the verdict (APPROVE or REQUEST CHANGES) and detailed reasoning. Users always see the complete rationale for any feedback, enabling them to understand and address concerns.

### Failed Review

If the AI API call fails before producing a non-empty review file (e.g., missing credentials, HTTP error, empty response), a fallback notice is posted instead:

```
## Claude AI Code Review - Failed
The Claude review failed to complete. Check [Actions](URL) for error details.
```

This ensures users are aware that a review was attempted and directs them to the Actions logs for debugging.

### File-Existence Guard

Both workflows use the POSIX test `[ -s /tmp/<reviewer>_review_body.md ]` to distinguish between:

1. **File exists and non-empty** (`-s` returns true): API call succeeded → post full review
2. **File missing or empty** (`-s` returns false): API call failed → post fallback notice

This guard is robust to cancellations, timeouts, and partial failures.

## Fallback Mechanisms

### PR Comment

The primary posting mechanism is `gh pr comment`, which posts the review as a comment visible to all PR viewers.

### Failure handling

If the PR comment posting fails (e.g., due to GitHub API rate limits or network issues), the error is visible in the workflow logs. The review is **not** written to `$GITHUB_STEP_SUMMARY`; if `gh pr comment` fails, the review content is only accessible in the raw workflow logs for that run.

> **Note:** Step-summary output was never implemented for these workflows — neither `claude-pr-review.yml` nor `gpt-pr-review.yml` writes to `$GITHUB_STEP_SUMMARY` (you can confirm this by grepping the workflow files). An earlier inline comment in the posting step claimed the review was "also in Actions summary"; that claim was inaccurate and has been corrected in the workflow YAML. The only reliable fallback when posting fails is the raw run logs.

## Workflow Step Configuration

- **`if: always()`**: The "Post review comment" step runs even if the verdict is REQUEST CHANGES (which exits the preceding step with a non-zero exit code). This ensures the full review is always visible.
- **`continue-on-error: true`**: If the gh pr comment call fails, the job does not fail. The failure is recorded in the workflow logs but does not block the overall workflow.

## Planned Improvements

- **`if: always() && !cancelled()`**: Tracked in #3289 (not yet merged). Once that PR lands, the posting step will be skipped if the workflow is cancelled, avoiding spurious failure notices when a workflow is superseded by a new push.

## Debugging

When a review fails to post, check the Actions logs for:

1. **API authentication errors**: Verify `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` secrets are configured
2. **Empty responses**: Check if the AI service is returning valid output
3. **Network/rate limit errors**: Review the raw workflow logs for the run; the review content will appear there if `gh pr comment` failed
4. **GitHub token issues**: Verify `GH_TOKEN` and PR permissions are correct

For more information, see the workflow files in `.github/workflows/`.
