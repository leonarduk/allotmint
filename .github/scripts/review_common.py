"""Shared helpers for advisory AI PR review scripts and workflows."""

from __future__ import annotations

from dataclasses import dataclass
import os
import sys

MAX_DIFF_CHARS = 30_000
DEFAULT_ISSUE_BODY = "No linked issue found. Review code on its own merits."
TRUNCATION_NOTICE_TEMPLATE = (
    "\n\n[diff truncated after {kept_files} file(s); skipped {skipped_files} additional file(s) "
    "to stay within the 30k-character review budget while preserving whole-file diff blocks]"
)


@dataclass(frozen=True)
class ReviewContext:
    """Environment-driven inputs shared by the GPT and Claude review scripts."""

    api_key: str
    pr_title: str
    diff: str
    issue_body: str


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise SystemExit with a clear error."""
    value = os.environ.get(name, "")
    if not value:
        print(f"ERROR: {name} not set", file=sys.stderr)
        raise SystemExit(1)
    return value


def load_review_context(api_key_env: str) -> ReviewContext:
    """Load the workflow inputs expected by the review scripts from environment variables.

    The workflows pass PR metadata through `PR_TITLE`, `DIFF`, and `ISSUE_BODY`, while the
    provider-specific secret must be present in `api_key_env`.
    """

    return ReviewContext(
        api_key=get_required_env(api_key_env),
        pr_title=os.environ.get("PR_TITLE", ""),
        diff=os.environ.get("DIFF", ""),
        issue_body=os.environ.get("ISSUE_BODY", DEFAULT_ISSUE_BODY),
    )


def build_prompt(pr_title: str, diff: str, issue_body: str) -> str:
    """Build the shared advisory review prompt used by both models."""
    return f"""You are a senior engineer reviewing a pull request for **allotmint**,
a family investment management app.

The stack is Python/FastAPI backend + React/Vite TypeScript frontend + AWS Lambda/CDK infrastructure.
Key constraints: preserve portfolio/compliance correctness, keep backend/frontend contracts aligned,
and avoid regressions in CI/deployment workflows.

## Linked issue / acceptance criteria
{issue_body}

## PR title
{pr_title}

## Diff (Python, TypeScript, JavaScript, JSON, Markdown, config files — truncated at 30k chars)
{diff}

If the diff is empty, this is likely a docs-only or config-only PR whose file types
were not captured. In that case, review the PR based solely on the linked issue
acceptance criteria and PR title, and note that no diff was available.

Review this PR across these dimensions. Be direct and specific — cite line numbers
or function names where relevant. If something looks fine, say so briefly.
Spend your words on real concerns.

### 1. Acceptance criteria
Does the diff satisfy every AC in the linked issue? Call out any gaps explicitly.
If no diff is available, assess whether the PR title and issue description suggest
the work is complete and correctly scoped.

### 2. Bugs and logic errors
Any incorrect behaviour, edge cases that aren't handled, or off-by-one errors?
For documentation PRs: are there factual errors, contradictions, or dangerously
misleading statements?

### 3. API, data, and workflow safety
- Do backend/frontend payload shapes still line up?
- Could this break local smoke tests, deployment workflows, or repo scripts?
- Are secrets, permissions, or CI assumptions handled safely?

### 4. Test coverage
Are the acceptance criteria actually exercised by tests or validation steps? Any obvious missing cases?
Not applicable for documentation-only PRs, but note if validation is missing.

### 5. Minor issues (optional)
Style, naming, docs — only flag if they would cause future confusion.

End with a one-line summary verdict: **APPROVE**, **REQUEST CHANGES**,
or **COMMENT** (no blocking concerns but worth noting)."""


def emit_empty_diff_notice(provider_name: str) -> int:
    """Exit cleanly when the filtered diff is empty instead of making a no-context API call."""
    print(
        f"No {provider_name} review generated because the filtered diff was empty. "
        "The workflow can still post this advisory note without failing."
    )
    return 0


def finalize_review(review: str, empty_error: str) -> int:
    """Print a non-empty review or fail with a clear error for workflow handling."""
    if not review.strip():
        print(empty_error, file=sys.stderr)
        return 1
    print(review.strip())
    return 0


def split_diff_blocks(diff_text: str) -> list[str]:
    """Split a git diff into whole-file blocks so truncation never cuts mid-file.

    Preserving complete `diff --git` blocks avoids mid-line truncation and helps keep YAML/JSON
    hunks structurally intelligible when the workflow must drop content to fit the model budget.
    """
    if not diff_text:
        return []

    blocks: list[str] = []
    current: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            blocks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("".join(current))
    return blocks


def truncate_diff(diff_text: str, limit: int = MAX_DIFF_CHARS) -> tuple[str, bool]:
    """Truncate a diff on whole-file boundaries and emit a notice when files are skipped.

    The 30k-character cap exists to stay within model context and comment-size budgets. When the
    diff is too large, we keep only complete file blocks that fit and append a short summary rather
    than slicing through a line or partial YAML/JSON structure.

    If every file block individually exceeds the limit (e.g. a single enormous file), we fall back
    to a hard line-boundary truncation of the first block so callers always receive non-empty output
    for a non-empty diff.
    """
    if len(diff_text) <= limit:
        return diff_text, False

    blocks = split_diff_blocks(diff_text)
    kept: list[str] = []
    used = 0

    for block in blocks:
        if len(block) > limit:
            continue
        projected = used + len(block)
        if projected > limit:
            break
        kept.append(block)
        used = projected

    if not kept:
        # Every block exceeds the limit individually.  Hard-truncate the first block at the
        # nearest line boundary so we still send something useful to the model.
        first_block = blocks[0] if blocks else diff_text
        hard_cut = first_block[:limit]
        if "\n" in hard_cut:
            hard_cut = hard_cut[: hard_cut.rfind("\n") + 1]
        notice = TRUNCATION_NOTICE_TEMPLATE.format(kept_files=0, skipped_files=len(blocks))
        return f"{hard_cut.rstrip()}{notice}", True

    skipped_files = max(len(blocks) - len(kept), 0)
    notice = TRUNCATION_NOTICE_TEMPLATE.format(
        kept_files=len(kept),
        skipped_files=skipped_files,
    )
    allowed_notice = max(limit - len(notice), 0)
    truncated = "".join(kept)
    if len(truncated) > allowed_notice:
        trimmed = truncated[:allowed_notice]
        truncated = trimmed[: trimmed.rfind("\n") + 1] if "\n" in trimmed else ""
    return f"{truncated.rstrip()}{notice}", True


def count_changed_files(diff_text: str) -> int:
    """Count diff file headers for workflow logging."""
    return sum(1 for line in diff_text.splitlines() if line.startswith("diff --git "))


def format_truncation_log(original_diff: str, truncated_diff: str) -> str:
    """Return a concise stderr message for workflow logs when truncation occurs."""
    return (
        "INFO: Truncated review diff from "
        f"{len(original_diff)} to {len(truncated_diff)} characters across "
        f"{count_changed_files(original_diff)} file block(s) to preserve whole diff sections."
    )
