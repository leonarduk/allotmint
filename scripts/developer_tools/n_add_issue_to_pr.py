"""CLI tool to retroactively link open PRs to a GitHub issue.

Continues the a_/b_/.../m_ script chain in scripts/developer_tools/. Every PR
is supposed to close an issue (see docs/CONTRIBUTING.md's branch/PR policy),
but a PR opened without going through d_work_on_issue.py/k_publish-pr.ps1 can
slip through without a "Closes #NNNN" reference. This script finds open PRs
whose body doesn't reference an issue, creates a matching issue from the PR's
own title/body, and appends "Closes #<new-issue>" to the PR description so
merging it auto-closes the new issue.

Safety:
  - Defaults to dry-run. Pass --yes to actually create issues and edit PRs.
  - Never touches a PR whose body already references an issue via
    Closes/Fixes/Resolves #NNNN (case-insensitive).
  - Only ever creates a new issue and appends to a PR's existing body; never
    deletes or overwrites existing PR body content.

Requires the `gh` CLI to be authenticated with a token that can create issues
and edit PRs on the target repo. Defaults to operating on the `origin` git
remote's repo; pass --repo owner/name to override.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_OWNER = "leonarduk"
REPO_NAME = "allotmint"
GH_RETRY_ATTEMPTS = 3
GH_RETRY_BACKOFF_SECONDS = 2
GH_TIMEOUT_SECONDS = 60

# Matches "Closes #123", "fixes: #45", "Resolved #7", etc. -- the same set of
# GitHub auto-close keywords recognised in a PR description, case-insensitive.
ISSUE_REF_PATTERN = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)", re.IGNORECASE
)


@dataclass
class PullRequest:
    """A single open pull request under consideration."""

    number: int
    title: str
    body: str
    author: str = ""


def _run_gh_once(
    args: list[str], timeout: int = GH_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    """Run a single `gh` CLI command scoped to REPO_OWNER/REPO_NAME. Never raises.

    A timed-out process is reported as a failing CompletedProcess rather than
    propagating subprocess.TimeoutExpired, so callers can uniformly check
    `result.returncode`.
    """
    cmd = ["gh", *args, "--repo", f"{REPO_OWNER}/{REPO_NAME}"]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, returncode=124, stdout="", stderr=f"gh {' '.join(args)} timed out after {timeout}s"
        )


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` CLI command scoped to REPO_OWNER/REPO_NAME. Never raises.

    Retries transient failures (network blips, GraphQL timeouts) up to
    GH_RETRY_ATTEMPTS times with a linear backoff. Only safe for idempotent
    (read-only) commands -- use `_run_gh_once` directly for non-idempotent
    operations like creating an issue or editing a PR, where a retry after a
    lost response could re-invoke the action.
    """
    result = None
    for attempt in range(1, GH_RETRY_ATTEMPTS + 1):
        result = _run_gh_once(args)
        if result.returncode == 0:
            return result
        if attempt < GH_RETRY_ATTEMPTS:
            wait_seconds = GH_RETRY_BACKOFF_SECONDS * attempt
            print(
                f"WARNING: gh {' '.join(args)} failed (attempt {attempt}/{GH_RETRY_ATTEMPTS}): "
                f"{result.stderr.strip()} -- retrying in {wait_seconds}s",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)
    return result


def fetch_open_prs(limit: int = 200) -> list[PullRequest]:
    """List open PRs with their number/title/body/author."""
    result = run_gh(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number,title,body,author",
            "--limit",
            str(limit),
        ]
    )
    if result.returncode != 0:
        print(f"ERROR: gh pr list failed: {result.stderr}", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"ERROR: gh pr list returned non-JSON output: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    prs = []
    for item in data:
        prs.append(
            PullRequest(
                number=item["number"],
                title=item["title"],
                body=item.get("body") or "",
                author=(item.get("author") or {}).get("login", ""),
            )
        )
    return prs


def fetch_pr(number: int) -> PullRequest:
    """Fetch a single PR by number."""
    result = run_gh(["pr", "view", str(number), "--json", "number,title,body,author"])
    if result.returncode != 0:
        print(f"ERROR: gh pr view {number} failed: {result.stderr}", file=sys.stderr)
        raise SystemExit(1)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"ERROR: gh pr view {number} returned non-JSON output: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return PullRequest(
        number=data["number"],
        title=data["title"],
        body=data.get("body") or "",
        author=(data.get("author") or {}).get("login", ""),
    )


def has_linked_issue(body: str) -> bool:
    """Return True if the PR body already references an issue via a close keyword."""
    return bool(ISSUE_REF_PATTERN.search(body or ""))


def build_issue_body(pr: PullRequest) -> str:
    """Build a structured issue body from a PR's own title/body."""
    pr_body = (pr.body or "").strip()
    how = pr_body if pr_body else "See PR for implementation details."
    parts = [
        "## What",
        "",
        pr.title,
        "",
        "## Why",
        "",
        f"Opened as PR #{pr.number} without an associated issue; this issue was "
        "created retroactively for traceability.",
        "",
        "## How",
        "",
        how,
        "",
        "## Files Affected",
        "",
        f"See PR #{pr.number} for the file list.",
        "",
        "## Constraints",
        "",
        "None",
        "",
        "## LLM tier",
        "",
        "sonnet",
        "",
        "## Success looks like",
        "",
        f"- [ ] PR #{pr.number} is merged with this issue linked and closed",
        "",
        "## Failure looks like",
        "",
        "- PR merges without this issue being closed",
    ]
    return "\n".join(parts)


def create_issue(pr: PullRequest, dry_run: bool) -> int | None:
    """Create an issue for a PR that lacks one. Returns the new issue number, or None on failure."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Creating issue for PR #{pr.number}: {pr.title}")
    if dry_run:
        return None

    body = build_issue_body(pr)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as tf:
        tf.write(body)
        body_path = tf.name
    try:
        result = _run_gh_once(["issue", "create", "--title", pr.title, "--body-file", body_path])
    finally:
        Path(body_path).unlink(missing_ok=True)

    if result.returncode != 0:
        print(
            f"ERROR: failed to create issue for PR #{pr.number}: {result.stderr}", file=sys.stderr
        )
        return None

    url = result.stdout.strip()
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        print(f"ERROR: could not parse issue number from gh output: {url!r}", file=sys.stderr)
        return None
    issue_number = int(match.group(1))
    print(f"[OK] Created issue #{issue_number}: {url}")
    return issue_number


def link_issue_to_pr(pr: PullRequest, issue_number: int, dry_run: bool) -> bool:
    """Append a 'Closes #NNNN' line to the PR body so merging auto-closes the issue."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Linking PR #{pr.number} to issue #{issue_number}")
    if dry_run:
        return True

    closing_line = f"Closes #{issue_number}"
    new_body = f"{pr.body.rstrip()}\n\n{closing_line}\n" if pr.body.strip() else f"{closing_line}\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as tf:
        tf.write(new_body)
        body_path = tf.name
    try:
        result = _run_gh_once(["pr", "edit", str(pr.number), "--body-file", body_path])
    finally:
        Path(body_path).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"ERROR: failed to update PR #{pr.number}: {result.stderr}", file=sys.stderr)
        return False
    print(f"[OK] PR #{pr.number} now closes #{issue_number}")
    return True


def process_pr(pr: PullRequest, dry_run: bool) -> bool:
    """Create and link an issue for a single PR, if it doesn't already have one.

    Returns False only when a create/link step was attempted and failed;
    skipping an already-linked PR is not treated as a failure.
    """
    if has_linked_issue(pr.body):
        print(f"SKIP: PR #{pr.number} ({pr.title}) already references an issue")
        return True

    issue_number = create_issue(pr, dry_run)
    if dry_run:
        return True
    if issue_number is None:
        return False
    return link_issue_to_pr(pr, issue_number, dry_run)


def resolve_repo(explicit: str | None) -> tuple[str, str]:
    """Resolve the (owner, repo) to operate on.

    Precedence: an explicit `--repo owner/name` flag, then the `origin` git
    remote, then the hardcoded REPO_OWNER/REPO_NAME fallback.
    """
    if explicit:
        owner, _, name = explicit.partition("/")
        if not owner or not name:
            print(f"ERROR: --repo must be in 'owner/name' form, got '{explicit}'", file=sys.stderr)
            raise SystemExit(1)
        return owner, name

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode == 0:
        match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", result.stdout.strip())
        if match:
            return match.group(1), match.group(2)

    return REPO_OWNER, REPO_NAME


def main() -> int:
    """Run the retroactive issue-linking flow."""
    parser = argparse.ArgumentParser(
        description="Create and link issues for open PRs that don't reference one"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually create issues and edit PRs. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository to operate on as 'owner/name'. Defaults to the 'origin' git "
        "remote, falling back to leonarduk/allotmint.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="Operate on a single PR number instead of scanning all open PRs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of open PRs to fetch when scanning (default 200).",
    )
    args = parser.parse_args()
    dry_run = not args.yes

    global REPO_OWNER, REPO_NAME
    REPO_OWNER, REPO_NAME = resolve_repo(args.repo)

    print(f"INFO: Operating on {REPO_OWNER}/{REPO_NAME}", file=sys.stderr)
    if args.pr:
        prs = [fetch_pr(args.pr)]
    else:
        prs = fetch_open_prs(args.limit)
        print(f"INFO: {len(prs)} open PR(s) found", file=sys.stderr)

    unlinked = [pr for pr in prs if not has_linked_issue(pr.body)]
    print(f"INFO: {len(unlinked)} PR(s) without a linked issue", file=sys.stderr)

    if dry_run:
        print("INFO: Running in dry-run mode. Pass --yes to actually create/link.", file=sys.stderr)

    had_failures = False
    for pr in prs:
        if not process_pr(pr, dry_run):
            had_failures = True

    return 1 if had_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
