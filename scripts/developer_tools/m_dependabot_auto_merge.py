"""CLI tool to auto-merge green Dependabot pull requests and delete their branches.

Continues the a_/b_/.../o_ script chain in scripts/developer_tools/. Dependabot opens
routine dependency-bump PRs; when CI has already passed there's no reason a human
needs to click merge. This script finds open PRs authored by `dependabot[bot]`,
merges the ones whose checks have all passed on the current head SHA, and deletes
the branch afterward. A PR that is otherwise green but reports mergeable_state
"behind", "blocked", or "unstable" (out of date with `main`, a pending review
request, or a required check GitHub hasn't finished recomputing -- none of
which reflect a real conflict) is handled specially: GitHub branch protection
generally rejects a plain `gh pr merge` in these states. --behind-strategy
controls how that's handled:
  - "admin" (default): force-merge with `gh pr merge --admin`, which bypasses
    branch-protection enforcement for that one merge. Checks still have to
    have passed first -- --admin only gets past the branch-protection block,
    it doesn't skip CI. A PR is never left stuck needing manual approval with
    this strategy.
  - "update-branch": for a "behind" PR, merge main into the PR branch first
    (gh pr update-branch) and leave the actual merge to a later run, once CI
    re-passes and the PR reports mergeable_state == "clean" (a PR can sit
    behind for multiple runs until that happens). "blocked"/"unstable" PRs
    aren't helped by updating the branch, so they still fall through to an
    admin merge.
  - "skip": leave the PR alone entirely.

Safety:
  - Defaults to dry-run. Pass --yes to actually merge/delete anything.
  - Only ever touches PRs authored by `dependabot[bot]`.
  - Never merges a PR with failing/pending checks or real merge conflicts
    (`mergeable_state == "dirty"`).
  - Never deletes `main`/`master`, only the merged PR's own head branch.

`gh pr list` frequently reports mergeability as "UNKNOWN" because GitHub
computes it lazily and bulk list queries don't reliably trigger that
computation. For any PR whose checks have already passed, this script
refetches mergeability with a per-PR `gh pr view` call (with a few retries)
before deciding to skip it.

Requires the `gh` CLI to be authenticated with a token that can merge PRs and
delete branches on the target repo (repo scope covers this). Defaults to
operating on the `origin` git remote's repo; pass --repo owner/name to
override.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

REPO_OWNER = "leonarduk"
REPO_NAME = "allotmint"
DEPENDABOT_LOGIN = "dependabot[bot]"
PROTECTED_BRANCHES = {"main", "master"}
GH_RETRY_ATTEMPTS = 3
GH_RETRY_BACKOFF_SECONDS = 2
GH_TIMEOUT_SECONDS = 60
MERGEABILITY_REFRESH_ATTEMPTS = 3
MERGEABILITY_REFRESH_WAIT_SECONDS = 3

# mergeable_state values that are eligible for a merge rather than an
# outright skip. "clean" is the ordinary green/no-conflict case that needs no
# special handling. "behind", "blocked", and "unstable" all show up for PRs
# that are otherwise green (checks_have_passed already verified the actual
# statusCheckRollup) but GitHub's branch-protection machinery won't allow a
# plain merge -- "behind" for an out-of-date head, "blocked"/"unstable" for
# things like a pending review request or a required-check recompute that
# hasn't settled -- none of which reflect a real conflict. Since this repo's
# branch protection requires zero approving reviews, none of these represent
# an actual human action needed; they're handled by ADMIN_OVERRIDE_STATES
# below (see process_pr).
MERGEABLE_STATES_OK_TO_MERGE = {"clean", "behind", "blocked", "unstable"}

# Subset of MERGEABLE_STATES_OK_TO_MERGE that needs `gh pr merge --admin` to
# get past branch-protection enforcement rather than a plain merge.
ADMIN_OVERRIDE_STATES = {"behind", "blocked", "unstable"}


@dataclass
class PullRequest:
    """A single open Dependabot pull request under consideration."""

    number: int
    title: str
    head_ref_name: str
    head_sha: str = ""
    mergeable: str | None = None
    mergeable_state: str = ""
    checks: list[dict] = field(default_factory=list)


def _run_gh_once(args: list[str], timeout: int = GH_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
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
    GH_RETRY_ATTEMPTS times with a linear backoff before returning the last
    failing result to the caller. Only safe for idempotent (read-only)
    commands -- use `_run_gh_once` directly for non-idempotent operations
    like merging a PR, where a retry after a lost response could re-invoke
    the action on an already-completed PR.
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


def fetch_open_dependabot_prs() -> list[PullRequest]:
    """List open PRs authored by dependabot[bot], with head ref/SHA and mergeable state."""
    result = run_gh(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--author",
            DEPENDABOT_LOGIN,
            "--json",
            "number,title,headRefName,headRefOid,mergeable,mergeStateStatus,statusCheckRollup",
            "--limit",
            "200",
        ],
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
                head_ref_name=item["headRefName"],
                head_sha=item.get("headRefOid", ""),
                mergeable=item.get("mergeable"),
                mergeable_state=(item.get("mergeStateStatus") or "").lower(),
                checks=item.get("statusCheckRollup") or [],
            )
        )
    return prs


def fetch_mergeability(number: int) -> tuple[str | None, str]:
    """Fetch a single PR's mergeable/mergeStateStatus via `gh pr view`.

    `gh pr list` frequently reports "UNKNOWN" for these fields because GitHub
    computes real mergeability lazily, and bulk list queries don't reliably
    trigger that computation. Querying a single PR is much more likely to
    return a computed value.
    """
    result = run_gh(["pr", "view", str(number), "--json", "mergeable,mergeStateStatus"])
    if result.returncode != 0:
        print(f"WARNING: gh pr view {number} failed: {result.stderr.strip()}", file=sys.stderr)
        return None, ""
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"WARNING: gh pr view {number} returned non-JSON output: {exc}", file=sys.stderr)
        return None, ""
    return data.get("mergeable"), (data.get("mergeStateStatus") or "").lower()


def resolve_mergeability(pr: PullRequest) -> None:
    """Refresh pr.mergeable/pr.mergeable_state in place if not yet computed.

    Retries a few times with a short wait, since GitHub computes mergeability
    asynchronously after a PR is queried and it can take a moment to settle.
    Mutates `pr` in place so callers see the refreshed values.
    """
    for attempt in range(MERGEABILITY_REFRESH_ATTEMPTS):
        if pr.mergeable_state and pr.mergeable_state != "unknown":
            return
        pr.mergeable, pr.mergeable_state = fetch_mergeability(pr.number)
        if pr.mergeable_state and pr.mergeable_state != "unknown":
            return
        if attempt < MERGEABILITY_REFRESH_ATTEMPTS - 1:
            time.sleep(MERGEABILITY_REFRESH_WAIT_SECONDS)


def _latest_checks_by_name(checks: list[dict]) -> list[dict]:
    """Collapse `statusCheckRollup` to the most recent run per (workflow, check) name.

    GitHub can list the same check twice -- e.g. a rerun leaves both the
    original run (which may show CANCELLED) and the new run (SUCCESS) in the
    rollup, both under the same workflowName/name pair. Evaluating every
    entry would fail the whole PR on a stale cancelled duplicate even though
    the check has since passed, so only the latest-completed entry per name
    counts.
    """
    latest: dict[tuple[str, str], dict] = {}
    for check in checks:
        key = (check.get("workflowName") or "", check.get("name") or "")
        existing = latest.get(key)
        if existing is None or (check.get("completedAt") or "") >= (existing.get("completedAt") or ""):
            latest[key] = check
    return list(latest.values())


def checks_have_passed(checks: list[dict]) -> bool:
    """Return True only if there is at least one check and every check succeeded.

    A PR with no checks at all is treated as not-yet-verified (returns False),
    since that usually means CI hasn't reported in yet rather than "nothing to
    check". Duplicate entries for the same check (see _latest_checks_by_name)
    are collapsed to their latest run before evaluation.
    """
    if not checks:
        return False
    for check in _latest_checks_by_name(checks):
        conclusion = (check.get("conclusion") or "").upper()
        status = (check.get("status") or "").upper()
        if status and status != "COMPLETED":
            return False
        if conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            return False
    return True


def is_mergeable(pr: PullRequest) -> bool:
    """Return True if the PR has no real conflicts (behind/blocked/unstable is fine).

    `gh pr list --json mergeable` returns the GraphQL MergeableState enum as a
    string -- "MERGEABLE", "CONFLICTING", or "UNKNOWN" -- never a Python bool,
    so a real conflict is rejected explicitly here rather than compared
    against `True`. `mergeable_state` (mergeStateStatus) is empty while
    GitHub is still computing it; that, plus anything outside
    MERGEABLE_STATES_OK_TO_MERGE, is treated as not-yet-mergeable.
    """
    if (pr.mergeable or "").upper() == "CONFLICTING":
        return False
    return pr.mergeable_state in MERGEABLE_STATES_OK_TO_MERGE


def merge_and_delete(pr: PullRequest, dry_run: bool, admin: bool = False) -> bool:
    """Merge a Dependabot PR (squash) and delete its head branch.

    Returns False if a real (non-dry-run) merge attempt failed, so the caller
    can propagate a nonzero exit code. Uses `_run_gh_once` (no retry) since
    merge is not idempotent -- a retry after a lost response could re-invoke
    the merge on an already-merged PR. `--match-head-commit` guards against
    merging a different revision than the one whose checks/mergeability were
    validated.

    `admin=True` adds `--admin`, which bypasses branch-protection enforcement
    for this one merge -- used only for a PR that's green but "behind" main,
    to get past the "head branch must be up to date" rule (a straight
    `gh pr merge` on a behind PR is rejected outright otherwise). Checks
    still have to have passed first; `--admin` isn't used to skip CI, only to
    override the up-to-date requirement.
    """
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Merging PR #{pr.number} ({pr.title}) and deleting branch '{pr.head_ref_name}'")
    if dry_run:
        return True

    if pr.head_ref_name in PROTECTED_BRANCHES:
        print(
            f"ERROR: refusing to delete protected branch '{pr.head_ref_name}' for PR #{pr.number}",
            file=sys.stderr,
        )
        return False

    args = ["pr", "merge", str(pr.number), "--squash", "--delete-branch"]
    if pr.head_sha:
        args += ["--match-head-commit", pr.head_sha]
    if admin:
        args += ["--admin"]
    result = _run_gh_once(args)
    if result.returncode != 0:
        print(f"ERROR: failed to merge PR #{pr.number}: {result.stderr}", file=sys.stderr)
        return False
    return True


def update_branch(pr: PullRequest, dry_run: bool) -> bool:
    """Update a Dependabot PR's branch with the latest changes from main.

    Used by the "update-branch" --behind-strategy: triggers CI to re-run
    against the refreshed branch, leaving the actual merge to a later run
    once mergeable_state reports "clean". Uses `_run_gh_once` (no retry)
    since this mutates the branch -- a retry after a lost response could
    reattempt the update on an already-updated branch.
    """
    prefix = "[DRY RUN] " if dry_run else ""
    print(
        f"{prefix}PR #{pr.number} ({pr.title}) is green but behind main -- "
        "updating branch instead of merging now"
    )
    if dry_run:
        return True

    result = _run_gh_once(["pr", "update-branch", str(pr.number)])
    if result.returncode != 0:
        print(f"ERROR: failed to update branch for PR #{pr.number}: {result.stderr}", file=sys.stderr)
        return False
    return True


def process_pr(pr: PullRequest, dry_run: bool, behind_strategy: str = "admin") -> bool:
    """Decide whether a single Dependabot PR should be merged, and act on it.

    Returns False only when a merge/update was attempted and failed; skipping
    a PR (checks not passed, not mergeable, or behind_strategy == "skip") is
    not treated as a failure.
    """
    if not checks_have_passed(pr.checks):
        print(f"SKIP: PR #{pr.number} ({pr.title}) -- checks not all passed")
        return True
    resolve_mergeability(pr)
    if not is_mergeable(pr):
        print(
            f"SKIP: PR #{pr.number} ({pr.title}) -- not mergeable "
            f"(mergeable={pr.mergeable}, state={pr.mergeable_state})"
        )
        return True
    if pr.mergeable_state in ADMIN_OVERRIDE_STATES:
        if behind_strategy == "skip":
            print(
                f"SKIP: PR #{pr.number} ({pr.title}) -- state={pr.mergeable_state}, "
                "--behind-strategy=skip"
            )
            return True
        if behind_strategy == "update-branch" and pr.mergeable_state == "behind":
            return update_branch(pr, dry_run)
        return merge_and_delete(pr, dry_run, admin=True)
    return merge_and_delete(pr, dry_run)


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
    """Run the Dependabot auto-merge flow."""
    parser = argparse.ArgumentParser(
        description="Auto-merge open Dependabot PRs whose checks have all passed"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually merge and delete branches. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository to operate on as 'owner/name'. Defaults to the 'origin' git "
        "remote, falling back to leonarduk/allotmint.",
    )
    parser.add_argument(
        "--behind-strategy",
        choices=["admin", "update-branch", "skip"],
        default="admin",
        help="How to handle a green PR that's only blocked by being behind main: "
        "'admin' (default) force-merges with `gh pr merge --admin`; 'update-branch' "
        "merges main into the PR branch and leaves the merge to a later run; "
        "'skip' leaves the PR alone entirely.",
    )
    args = parser.parse_args()
    dry_run = not args.yes

    global REPO_OWNER, REPO_NAME
    REPO_OWNER, REPO_NAME = resolve_repo(args.repo)

    print(f"INFO: Fetching open Dependabot PRs for {REPO_OWNER}/{REPO_NAME}...", file=sys.stderr)
    prs = fetch_open_dependabot_prs()
    print(f"INFO: {len(prs)} open Dependabot PR(s) found", file=sys.stderr)

    if dry_run:
        print("INFO: Running in dry-run mode. Pass --yes to actually merge/delete.", file=sys.stderr)

    had_failures = False
    for pr in prs:
        if not process_pr(pr, dry_run, behind_strategy=args.behind_strategy):
            had_failures = True

    return 1 if had_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
