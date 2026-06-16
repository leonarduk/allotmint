"""Shared helpers for advisory AI PR review scripts and workflows."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

MAX_DIFF_CHARS = 120_000
DEFAULT_ISSUE_BODY = "No linked issue found. Review code on its own merits."
TRUNCATION_NOTICE_TEMPLATE = (
    "\n\n[diff truncated after {kept_files} file(s); skipped {skipped_files} additional file(s) "
    "to stay within the 120k-character review budget while preserving whole-file diff blocks]"
)


@dataclass(frozen=True)
class ReviewContext:
    """Environment-driven inputs shared by the GPT and Claude review scripts."""

    api_key: str
    pr_title: str
    diff: str
    issue_body: str
    discussion: str
    verified_facts: str = ""


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
        discussion=os.environ.get("DISCUSSION", ""),
        verified_facts=os.environ.get("VERIFIED_FACTS", ""),
    )


def build_discussion_section(discussion: str) -> str:
    """Return the prompt section covering discussion since the last review, if any."""
    if not discussion.strip():
        return ""
    return f"""

## Discussion since your last review
The following PR comments were posted after your last review (oldest first).
Treat them as **pointers**, not as proof. A comment claiming something is "fixed" or
"addressed" does not by itself clear a blocking concern. However, a comment that points
to a specific commit SHA or file:line reference may be treated as evidence the concern
was addressed; verify it against the diff if the relevant block is present. If a blocking
concern is only verbally dismissed with no code reference, you must still REQUEST CHANGES.

{discussion}"""


def build_prompt(pr_title: str, diff: str, issue_body: str, discussion: str = "", verified_facts: str = "") -> str:
    """Build the shared advisory review prompt used by both models."""
    discussion_section = build_discussion_section(discussion)
    verified_facts_section = f"\n- {verified_facts}" if verified_facts else ""
    return f"""You are a senior engineer reviewing a pull request for **allotmint**,
a family investment management app.

The stack is Python/FastAPI backend + React/Vite TypeScript frontend + AWS Lambda/CDK infrastructure.
Key constraints: preserve portfolio/compliance correctness, keep backend/frontend contracts aligned,
and avoid regressions in CI/deployment workflows.

## Repo-specific context (verified facts — do not raise these as issues)

- **`actions/checkout@v6` and `actions/setup-node@v6` are correct.** Dependabot bumped both from
  v4 to v6 in PRs #2954/#2953; they are the repo-wide convention. Do not flag them as
  non-existent or wrong.
- **`api.getVarBreakdown()` returns camelCase keys** (`varDate`, `varLossPercent`, `scenarios`,
  `breakdown`). The function in `frontend/src/api.ts` transforms the snake_case backend response
  before returning. Test mocks that use camelCase for this function are correct.
- **`recomputeValueAtRisk` is fire-and-forget** in `ValueAtRisk.tsx`. After calling it, the
  component does not re-fetch `getValueAtRisk`; a period change or page refresh triggers the next
  fetch. Tests asserting `getValueAtRisk` is called only once after a recompute are correct.
- **`frontend/package-lock.json` contains Linux-specific optional peer deps** (e.g.
  `@emnapi/core`, `@emnapi/runtime`) that do not appear when the lock file is regenerated on
  Windows. Do not suggest regenerating or normalising the lock file on a non-Linux machine.{verified_facts_section}

## Linked issue / acceptance criteria
{issue_body}

## PR title
{pr_title}

## Diff (Python, TypeScript, JavaScript, JSON, Markdown, HTML, config files, shell scripts (.sh), PowerShell scripts (.ps1) — truncated at 120k chars)
{diff}

If the diff is empty, this is likely a docs-only or config-only PR whose file types
were not captured. In that case, review the PR based solely on the linked issue
acceptance criteria and PR title, and note that no diff was available.
{discussion_section}

Review this PR across these dimensions. Be direct and specific — cite line numbers
or function names where relevant. Spend your words on real concerns.

**Omit any section entirely if you have nothing to say about it.**
Do not write "No issues found" or placeholder text for empty sections — just skip them.

### 1. Acceptance criteria
Does the diff satisfy every AC in the linked issue? Call out any gaps explicitly.
If no diff is available, assess whether the PR title and issue description suggest
the work is complete and correctly scoped.

### 2. Bugs and logic errors
Blocking only: incorrect behaviour, unhandled edge cases, off-by-one errors, or
security/data-loss risks. For documentation PRs: factual errors or dangerously
misleading statements.

### 3. API, data, and workflow safety
Blocking only:
- Backend/frontend payload shapes misaligned?
- Could this break local smoke tests, deployment workflows, or repo scripts?
- Secrets, permissions, or CI assumptions mishandled?

### 4. Test coverage
Are the acceptance criteria exercised by tests or validation steps? Note obvious
missing cases only if they represent a real regression risk.

### 5. Suggested follow-up issues (optional)
For non-blocking improvements (style consistency, missing lockfile, refactor
opportunities, test coverage gaps, etc.) that are real but should not block
this PR: list each as a one-line suggested GitHub issue title. Do not request
changes for these — they belong in the backlog, not this review.

End with a **verdict line** in exactly this format (do not add backticks around the verdict):

- `**APPROVE**` — no blocking concerns (non-blocking items go in section 5 above)
- `**REQUEST CHANGES**` — one or more blocking bugs, security issues, or unmet AC items (list them)

Do not use COMMENT as a verdict. If there are only non-blocking observations,
use APPROVE and put them in section 5."""


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


def extract_filenames_from_diff(diff_text: str) -> list[str]:
    """Extract filenames from diff in order of appearance."""
    filenames = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            # Extract filename from "diff --git a/path/to/file b/path/to/file"
            parts = line.split()
            if len(parts) >= 4:
                # Get the filename (remove a/ and b/ prefixes)
                filename = parts[3]
                if filename.startswith("b/"):
                    filename = filename[2:]
                filenames.append(filename)
    return filenames


def extract_important_filenames(text: str) -> set[str]:
    """Extract filenames mentioned in text (PR title or issue body)."""
    import re
    filenames = set()
    for match in re.finditer(r'\b[\w\-./]+\.(?:py|ts|tsx|js|json|yml|yaml|sh|ps1)\b', text):
        filenames.add(match.group(0))
    return filenames


def prioritize_diff_blocks(diff_text: str, pr_title: str = "", issue_body: str = "") -> list[str]:
    """Split and prioritize diff blocks by importance.

    Returns blocks sorted so that files mentioned in PR title/issue come first,
    followed by other changed files.
    """
    blocks = split_diff_blocks(diff_text)
    if not blocks or not (pr_title or issue_body):
        return blocks

    # Extract filenames mentioned in PR title and issue body
    important_files = extract_important_filenames(f"{pr_title} {issue_body}")

    # Extract filename for each block
    def get_block_filename(block: str) -> str:
        for line in block.splitlines():
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) >= 4:
                    filename = parts[3]
                    if filename.startswith("b/"):
                        filename = filename[2:]
                    return filename
        return ""

    # Sort blocks: important files first, then others
    important_blocks = [b for b in blocks if get_block_filename(b) in important_files]
    other_blocks = [b for b in blocks if get_block_filename(b) not in important_files]

    return important_blocks + other_blocks


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

    The 60k-character cap exists to stay within model context and comment-size budgets. When the
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


def fetch_review(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    extractor: Callable[[dict[str, Any]], tuple[str, dict[str, Any]]],
    provider_label: str,
) -> tuple[str, dict[str, Any]]:
    """POST `payload` to `url` and return the review text plus provider-specific extras.

    Shared by the Claude and GPT review scripts: handles the HTTP POST, timeout,
    `HTTPError` reporting, and empty-response warning so each script only has to
    supply its endpoint, headers, payload, and an `extractor` that turns the parsed
    JSON response into `(review_text, extra)`. `extra` carries provider-specific
    metadata (e.g. Claude's `stop_reason`) back to the caller.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )

    status: int | None = None
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = getattr(response, "status", None)
            raw = response.read()
            print(
                f"INFO: {provider_label} API responded status={status} bytes={len(raw)}",
                file=sys.stderr,
            )
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Keep the provider response in stderr so maintainers can distinguish auth, quota, and API failures.
        body = exc.read().decode()
        print(f"ERROR: {provider_label} API returned {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"ERROR: {provider_label} API request failed: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        print(f"ERROR: {provider_label} API returned non-JSON response: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    review, extra = extractor(data)
    if not review.strip():
        print(
            f"WARNING: {provider_label} API returned an empty review body (status={status})",
            file=sys.stderr,
        )
    return review, extra
