"""CLI tool to retroactively link open PRs to a GitHub issue.

Continues the a_/b_/.../o_ script chain in scripts/developer_tools/. Every PR
is supposed to close an issue (see docs/CONTRIBUTING.md), but a PR opened by
hand, or by an external contributor, can slip through without a
"Closes #NNNN" reference. This script finds open PRs whose body doesn't
reference an issue, creates a matching issue from the PR's own title/body
(using the standard bug_report.md template sections), and appends the closing
syntax to the PR description so GitHub links the two and closes the issue
automatically once the PR merges.

Safety:
  - Defaults to dry-run: prints what would be created/edited without doing
    it. Pass --yes to actually create issues and edit PR descriptions.
  - Never touches a PR whose body already references an issue via
    Closes/Close/Closed/Fixes/Fix/Fixed/Resolves/Resolve/Resolved
    (case-insensitive) -- those are left alone.

Requires the `gh` CLI to be authenticated with a token that can create
issues and edit PR descriptions on the target repo (repo scope covers this).
Defaults to operating on the `origin` git remote's repo; pass --repo
owner/name to override.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info

GH_TIMEOUT_SECONDS = 60
DEFAULT_VALUE_LABEL = "Medium Value"

ISSUE_REF_PATTERN = re.compile(
    r"\b(closes?|closed|fix(?:es|ed)?|resolves?|resolved)\s*:?\s*#(\d+)",
    re.IGNORECASE,
)


@dataclass
class PullRequest:
    """A single open pull request under consideration."""

    number: int
    title: str
    body: str
    files: list[str] = field(default_factory=list)


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a single `gh` CLI command. Never raises."""
    cmd = ["gh", *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, returncode=124, stdout="", stderr=f"gh {' '.join(args)} timed out"
        )


def has_linked_issue(pr_body: str) -> bool:
    """Return True if the PR body already references an issue via a closing keyword."""
    return bool(ISSUE_REF_PATTERN.search(pr_body or ""))


def fetch_open_prs(owner: str, repo: str) -> list[PullRequest]:
    """List open PRs (title, body, changed files) for the given repo."""
    result = run_gh(
        [
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--state",
            "open",
            "--json",
            "number,title,body,files",
            "--limit",
            "200",
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
        files = [f["path"] for f in (item.get("files") or []) if f.get("path")]
        prs.append(
            PullRequest(
                number=item["number"],
                title=item["title"],
                body=item.get("body") or "",
                files=files,
            )
        )
    return prs


def build_issue_body(pr: PullRequest) -> str:
    """Build a bug_report.md-shaped issue body describing a retroactive link to `pr`."""
    what = pr.body.strip() or f"See PR #{pr.number} for details."
    files_affected = "\n".join(pr.files) if pr.files else f"See PR #{pr.number} diff."
    parts = [
        "## What",
        "",
        f"This issue was retroactively created to link PR #{pr.number}, which had "
        "no linked issue.",
        "",
        what,
        "",
        "## Why",
        "",
        "To ensure every pull request is associated with an issue before merging, "
        "for traceability and documentation.",
        "",
        "## How",
        "",
        f"Already implemented in PR #{pr.number}. See the PR diff for the change.",
        "",
        "## Files Affected",
        "",
        files_affected,
        "",
        "## Constraints",
        "",
        "None",
        "",
        "## LLM tier",
        "",
        "sonnet",
        "",
        "## Value",
        "",
        DEFAULT_VALUE_LABEL,
        "",
        "## Success looks like",
        "",
        f"- [ ] PR #{pr.number} is merged",
        "",
        "## Failure looks like",
        "",
        f"- PR #{pr.number} is closed without merging",
    ]
    return "\n".join(parts)


def create_issue(owner: str, repo: str, title: str, body: str, labels: list[str]) -> int | None:
    """Create an issue via the `gh` CLI. Returns the new issue number, or None on failure."""
    body_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tf:
            tf.write(body)
            body_path = tf.name

        args = [
            "issue",
            "create",
            "--repo",
            f"{owner}/{repo}",
            "--title",
            title,
            "--body-file",
            body_path,
        ]
        for label in labels:
            args += ["--label", label]

        result = run_gh(args)
        if result.returncode != 0:
            print(f"ERROR: gh issue create failed: {result.stderr.strip()}", file=sys.stderr)
            return None

        match = re.search(r"/issues/(\d+)", result.stdout)
        if not match:
            print(
                f"ERROR: could not parse issue number from gh output: {result.stdout!r}",
                file=sys.stderr,
            )
            return None
        return int(match.group(1))
    finally:
        if body_path and Path(body_path).exists():
            Path(body_path).unlink()


def update_pr_body(owner: str, repo: str, pr: PullRequest, issue_number: int) -> bool:
    """Append a `Closes #NNNN` line to the PR body via the `gh` CLI."""
    new_body = pr.body.rstrip()
    new_body += f"\n\nCloses #{issue_number}" if new_body else f"Closes #{issue_number}"

    body_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tf:
            tf.write(new_body)
            body_path = tf.name

        result = run_gh(
            [
                "pr",
                "edit",
                str(pr.number),
                "--repo",
                f"{owner}/{repo}",
                "--body-file",
                body_path,
            ]
        )
        if result.returncode != 0:
            print(
                f"ERROR: gh pr edit failed for PR #{pr.number}: {result.stderr.strip()}",
                file=sys.stderr,
            )
            return False
        return True
    finally:
        if body_path and Path(body_path).exists():
            Path(body_path).unlink()


def process_pr(owner: str, repo: str, pr: PullRequest, dry_run: bool, labels: list[str]) -> bool:
    """Link a single unlinked PR to a newly created issue.

    Returns False only when a create/edit was attempted and failed; skipping
    an already-linked PR is not treated as a failure.
    """
    if has_linked_issue(pr.body):
        print(f"SKIP: PR #{pr.number} ({pr.title}) -- already references an issue")
        return True

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}PR #{pr.number} ({pr.title}) has no linked issue -- creating one")
    if dry_run:
        return True

    issue_body = build_issue_body(pr)
    issue_number = create_issue(owner, repo, pr.title, issue_body, labels)
    if issue_number is None:
        return False
    print(f"  Created issue #{issue_number}")

    if not update_pr_body(owner, repo, pr, issue_number):
        return False
    print(f"  Updated PR #{pr.number} body with 'Closes #{issue_number}'")
    return True


def resolve_repo(explicit: str | None) -> tuple[str, str]:
    """Resolve the (owner, repo) to operate on: an explicit --repo, else the origin remote."""
    if explicit:
        owner, _, name = explicit.partition("/")
        if not owner or not name:
            print(f"ERROR: --repo must be in 'owner/name' form, got '{explicit}'", file=sys.stderr)
            raise SystemExit(1)
        return owner, name

    try:
        return get_repo_info()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> int:
    """Run the retroactive issue-linking flow."""
    parser = argparse.ArgumentParser(
        description="Create and link issues for open PRs that don't reference one"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually create issues and edit PR descriptions. Without this flag, "
        "runs in dry-run mode.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository to operate on as 'owner/name'. Defaults to the 'origin' git remote.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="Only process this single PR number instead of scanning all open PRs.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=None,
        help="Label to apply to created issues (repeatable). Defaults to 'bug' and "
        f"'{DEFAULT_VALUE_LABEL}'.",
    )
    args = parser.parse_args()
    dry_run = not args.yes
    labels = args.label or ["bug", DEFAULT_VALUE_LABEL]

    owner, repo = resolve_repo(args.repo)

    print(f"INFO: Fetching open PRs for {owner}/{repo}...", file=sys.stderr)
    prs = fetch_open_prs(owner, repo)
    if args.pr is not None:
        prs = [pr for pr in prs if pr.number == args.pr]
        if not prs:
            print(f"ERROR: PR #{args.pr} not found among open PRs", file=sys.stderr)
            return 1
    print(f"INFO: {len(prs)} open PR(s) to check", file=sys.stderr)

    if dry_run:
        print(
            "INFO: Running in dry-run mode. Pass --yes to actually create/edit anything.",
            file=sys.stderr,
        )

    had_failures = False
    for pr in prs:
        if not process_pr(owner, repo, pr, dry_run, labels):
            had_failures = True

    return 1 if had_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
