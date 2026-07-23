"""CLI tool to triage unmilestoned open issues using a local Ollama model.

Continues the a_/b_/c_/.../g_ script chain in scripts/developer_tools/. Replaces the
hosted "allotmint-issue-triage" scheduled cloud-agent task: a local model (driven via
lib/ollama_common.py, same pattern as e_local_review.py/g_pr_review.py) classifies
open, unmilestoned issues and this script drives the resulting `gh issue` calls
directly, so the routine no longer needs a hosted-Claude scheduled session.

Rules ported from the scheduled-task prompt:
  - Only issues with no milestone are ever touched; already-milestoned issues are
    never read from write-side gh calls.
  - Issues that explicitly scope themselves apart from another issue (e.g. "tracked
    separately as #N" or "Out of scope: #N") are never folded/duplicated together.
  - Duplicates/folds are closed with `gh issue close --reason "not planned"` plus an
    explanatory comment; issues are never deleted.
  - Fold groups become a single consolidator issue, matching the #5321/#5396 style.
  - Everything left gets the "Backend Hardening & Test Coverage" milestone, except
    issues the model flags as a genuine new feature, which are commented and skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from ollama_common import (  # noqa: E402
    fetch_ollama_review,
    get_ollama_endpoint,
    get_ollama_model,
    validate_ollama_connection,
)

REPO_OWNER = "leonarduk"
REPO_NAME = "allotmint"
CONSOLIDATOR_MILESTONE = "Backend Hardening & Test Coverage"

SCOPE_APART_PATTERN = re.compile(r"(?:tracked separately as|out of scope:?)\s*#(\d+)", re.IGNORECASE)
ISSUE_REF_PATTERN = re.compile(r"#(\d+)")
CLASSIFICATION_LINE_PATTERN = re.compile(r"#(\d+):\s*(DUPLICATE|FOLD|STANDALONE|NEW_FEATURE)", re.IGNORECASE)


@dataclass
class Issue:
    """A single open, unmilestoned GitHub issue under triage."""

    number: int
    title: str
    labels: list[str] = field(default_factory=list)
    body: str = ""


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` CLI command scoped to REPO_OWNER/REPO_NAME. Never raises."""
    return subprocess.run(
        ["gh", *args, "--repo", f"{REPO_OWNER}/{REPO_NAME}"],
        capture_output=True,
        text=True,
        check=False,
    )


def fetch_unmilestoned_open_issues() -> list[Issue]:
    """List open issues that have no milestone assigned."""
    result = run_gh(
        [
            "issue",
            "list",
            "--state",
            "open",
            "--json",
            "number,title,labels,milestone,createdAt",
            "--limit",
            "500",
        ]
    )
    if result.returncode != 0:
        print(f"ERROR: gh issue list failed: {result.stderr}", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"ERROR: gh issue list returned non-JSON output: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    issues = []
    for item in data:
        if item.get("milestone") is not None:
            continue
        labels = [label["name"] for label in item.get("labels", [])]
        issues.append(Issue(number=item["number"], title=item["title"], labels=labels))
    return issues


def fetch_issue_body(number: int) -> str:
    """Fetch the full body text of a single issue via `gh issue view`."""
    result = run_gh(["issue", "view", str(number), "--json", "body"])
    if result.returncode != 0:
        print(f"WARNING: gh issue view #{number} failed: {result.stderr}", file=sys.stderr)
        return ""
    try:
        return json.loads(result.stdout).get("body") or ""
    except json.JSONDecodeError:
        return ""


def is_scoped_apart(body: str, other_number: int) -> bool:
    """Return True if `body` explicitly scopes itself apart from `other_number`."""
    return any(int(m.group(1)) == other_number for m in SCOPE_APART_PATTERN.finditer(body))


def referenced_issue_numbers(body: str) -> set[int]:
    """Return every issue/PR number referenced with '#NNNN' in the body."""
    return {int(m.group(1)) for m in ISSUE_REF_PATTERN.finditer(body)}


def find_candidate_groups(issues: list[Issue]) -> list[list[Issue]]:
    """Group issues that plausibly duplicate/fold into each other.

    Two issues are grouped when one directly references the other's number (the
    common pattern for AI-review nit issues stamped from the same source PR), and
    neither has explicitly scoped itself apart from the other. Singletons that
    reference nothing else in the unmilestoned set are left out of the result.
    """
    by_number = {issue.number: issue for issue in issues}
    parent: dict[int, int] = {issue.number: issue.number for issue in issues}

    def find(n: int) -> int:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    for issue in issues:
        for ref in referenced_issue_numbers(issue.body):
            if ref not in by_number or ref == issue.number:
                continue
            other = by_number[ref]
            if is_scoped_apart(issue.body, ref) or is_scoped_apart(other.body, issue.number):
                continue
            union(issue.number, ref)

    groups: dict[int, list[Issue]] = {}
    for issue in issues:
        groups.setdefault(find(issue.number), []).append(issue)

    return [group for group in groups.values() if len(group) > 1]


GROUP_CLASSIFY_PROMPT_TEMPLATE = """You are triaging a group of GitHub issues from the allotmint \
repo that cross-reference each other. For each issue, decide whether it is:

- DUPLICATE: an exact or near-duplicate of another issue in the group (same fix, same scope)
- FOLD: a tight, narrow follow-up from the same source PR/theme, small enough that bundling it \
into one consolidator tracking issue with the others makes sense
- STANDALONE: related in theme but substantial/independent enough to keep as its own issue
- NEW_FEATURE: a genuinely new feature ask, not a hardening/test-coverage nit -- must never be \
folded or marked as a duplicate

Respond with exactly one line per issue, in this exact format and nothing else:
#<number>: <CLASSIFICATION>

Issues:
{issues_block}
"""

SINGLE_CLASSIFY_PROMPT_TEMPLATE = """You are triaging a single GitHub issue from the allotmint \
repo. Classify it as exactly one of:

- NEW_FEATURE: a genuine new feature or functionality request
- BACKLOG: a hardening, bug-fix, test-coverage, or refactor nit suitable for a general backend \
hardening/test-coverage backlog milestone

Respond with exactly one word: NEW_FEATURE or BACKLOG.

### #{number}: {title}
{body}
"""


def build_group_classification_prompt(group: list[Issue]) -> str:
    """Build the local-LLM prompt asking it to classify every issue in a candidate group."""
    blocks = [f"### #{issue.number}: {issue.title}\n{issue.body.strip()}\n" for issue in group]
    return GROUP_CLASSIFY_PROMPT_TEMPLATE.format(issues_block="\n".join(blocks))


def parse_classifications(response: str) -> dict[int, str]:
    """Parse the model's '#N: CLASSIFICATION' lines into a {number: classification} map."""
    return {int(m.group(1)): m.group(2).upper() for m in CLASSIFICATION_LINE_PATTERN.finditer(response)}


def classify_single_issue(issue: Issue, model: str, endpoint: str) -> str:
    """Classify a standalone issue as NEW_FEATURE or BACKLOG."""
    prompt = SINGLE_CLASSIFY_PROMPT_TEMPLATE.format(number=issue.number, title=issue.title, body=issue.body.strip())
    response = fetch_ollama_review(endpoint, model, prompt)
    return "NEW_FEATURE" if "NEW_FEATURE" in response.upper() else "BACKLOG"


def close_issue(number: int, comment: str, dry_run: bool) -> None:
    """Close an issue as 'not planned' with an explanatory comment. Never deletes."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Closing #{number} (not planned): {comment}")
    if dry_run:
        return
    run_gh(["issue", "close", str(number), "--reason", "not planned", "--comment", comment])


def assign_milestone(number: int, milestone: str, dry_run: bool) -> None:
    """Assign the consolidator milestone to an issue."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Assigning milestone '{milestone}' to #{number}")
    if dry_run:
        return
    run_gh(["issue", "edit", str(number), "--milestone", milestone])


def comment_new_feature(number: int, dry_run: bool) -> None:
    """Leave a comment explaining why a new-feature issue was left unmilestoned."""
    comment = (
        "Skipped automated triage: this looks like a genuine new-feature request rather than a "
        f"hardening/test-coverage nit, so it was not assigned to the '{CONSOLIDATOR_MILESTONE}' "
        "milestone. Please triage/milestone it manually."
    )
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Commenting on #{number} (new feature, skipped)")
    if dry_run:
        return
    run_gh(["issue", "comment", str(number), "--body", comment])


def create_consolidator_issue(title: str, folded: list[Issue], dry_run: bool) -> int | None:
    """Create a consolidator tracking issue, following the #5321/#5396 template.

    Returns the new issue number, or None in dry-run mode or on failure.
    """
    folded_refs = ", ".join(f"#{issue.number}" for issue in folded)
    scope_lines = "\n".join(f"- {issue.title}" for issue in folded)
    body = (
        "## Consolidated tracking issue\n\n"
        f"This replaces {len(folded)} related issues.\n\n"
        "### Folded issues\n"
        f"{folded_refs}\n\n"
        "### Scope\n"
        f"{scope_lines}\n\n"
        "Pick off items individually; not all need to land together.\n"
    )
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Creating consolidator issue: {title} (folding {folded_refs})")
    if dry_run:
        return None

    result = run_gh(
        [
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--milestone",
            CONSOLIDATOR_MILESTONE,
        ]
    )
    if result.returncode != 0:
        print(f"ERROR: failed to create consolidator issue: {result.stderr}", file=sys.stderr)
        return None
    match = re.search(r"/issues/(\d+)", result.stdout)
    return int(match.group(1)) if match else None


def triage_group(group: list[Issue], model: str, endpoint: str, dry_run: bool) -> set[int]:
    """Classify and act on one candidate group. Returns the issue numbers it handled."""
    prompt = build_group_classification_prompt(group)
    response = fetch_ollama_review(endpoint, model, prompt)
    classifications = parse_classifications(response)
    canonical = min(group, key=lambda issue: issue.number)

    handled: set[int] = set()
    fold_candidates: list[Issue] = []
    for issue in group:
        classification = classifications.get(issue.number, "STANDALONE")
        if classification == "NEW_FEATURE":
            comment_new_feature(issue.number, dry_run)
            handled.add(issue.number)
        elif classification == "DUPLICATE" and issue.number != canonical.number:
            close_issue(
                issue.number,
                f"Duplicate of #{canonical.number}, closing per automated triage.",
                dry_run,
            )
            handled.add(issue.number)
        elif classification == "FOLD":
            fold_candidates.append(issue)

    if len(fold_candidates) > 1:
        title = f"Consolidated follow-ups: {fold_candidates[0].title}"
        consolidator_number = create_consolidator_issue(title, fold_candidates, dry_run)
        for issue in fold_candidates:
            reference = f"#{consolidator_number}" if consolidator_number else "a new consolidator issue"
            close_issue(issue.number, f"Folded into {reference}.", dry_run)
            handled.add(issue.number)

    return handled


def triage_remaining(issues: list[Issue], model: str, endpoint: str, dry_run: bool) -> None:
    """Classify every issue not already handled by group triage, then act on it."""
    for issue in issues:
        classification = classify_single_issue(issue, model, endpoint)
        if classification == "NEW_FEATURE":
            comment_new_feature(issue.number, dry_run)
        else:
            assign_milestone(issue.number, CONSOLIDATOR_MILESTONE, dry_run)


def main() -> int:
    """Run the issue-triage flow."""
    parser = argparse.ArgumentParser(description="Triage open, unmilestoned issues using a local Ollama model")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the actions that would be taken without calling gh",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only consider the first N unmilestoned issues (useful for testing)",
    )
    args = parser.parse_args()

    endpoint = get_ollama_endpoint()
    if not validate_ollama_connection(endpoint):
        print(
            f"ERROR: Ollama is not reachable at {endpoint}. Please start Ollama or set OLLAMA_ENDPOINT.",
            file=sys.stderr,
        )
        return 1
    model = get_ollama_model()

    print(
        f"INFO: Fetching unmilestoned open issues from {REPO_OWNER}/{REPO_NAME}...",
        file=sys.stderr,
    )
    issues = fetch_unmilestoned_open_issues()
    if args.limit is not None:
        issues = issues[: args.limit]
    print(f"INFO: {len(issues)} unmilestoned open issues found", file=sys.stderr)

    for issue in issues:
        issue.body = fetch_issue_body(issue.number)

    print(f"INFO: Using Ollama model '{model}' at {endpoint}", file=sys.stderr)

    groups = find_candidate_groups(issues)
    handled: set[int] = set()
    for group in groups:
        handled |= triage_group(group, model, endpoint, args.dry_run)

    remaining = [issue for issue in issues if issue.number not in handled]
    triage_remaining(remaining, model, endpoint, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
