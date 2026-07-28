"""CLI tool to auto-merge green Dependabot pull requests and delete their branches.

Continues the a_/b_/.../h_ script chain in scripts/developer_tools/. Dependabot opens
routine dependency-bump PRs; when CI has already passed there's no reason a human
needs to click merge. This script finds open PRs authored by `dependabot[bot]`,
merges the ones whose checks have all passed on the current head SHA, and deletes
the branch afterward. A PR that is otherwise green but merely behind `main` (no
real conflicts) is still merged -- being behind alone should never block it.

Safety:
  - Defaults to dry-run. Pass --yes to actually merge/delete anything.
  - Only ever touches PRs authored by `dependabot[bot]`.
  - Never merges a PR with failing/pending checks or real merge conflicts
    (`mergeable_state == "dirty"`).
  - Never deletes `main`/`master`, only the merged PR's own head branch.

Requires the `gh` CLI to be authenticated with a token that can merge PRs and
delete branches on the target repo (repo scope covers this).
"""

from __future__ import annotations

import argparse
import json
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

# mergeable_state values that still permit a merge -- "behind" means only
# out-of-date with the base branch, which the issue explicitly asks us to
# merge anyway. "clean" is the ordinary green/no-conflict case.
MERGEABLE_STATES_OK_TO_MERGE = {"clean", "behind"}


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


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` CLI command scoped to REPO_OWNER/REPO_NAME. Never raises.

    Retries transient failures (network blips, GraphQL timeouts) up to
    GH_RETRY_ATTEMPTS times with a linear backoff before returning the last
    failing result to the caller.
    """
    result = None
    for attempt in range(1, GH_RETRY_ATTEMPTS + 1):
        result = subprocess.run(
            ["gh", *args, "--repo", f"{REPO_OWNER}/{REPO_NAME}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
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
                head_ref_name=item["headRefName"],
                head_sha=item.get("headRefOid", ""),
                mergeable=item.get("mergeable"),
                mergeable_state=(item.get("mergeStateStatus") or "").lower(),
                checks=item.get("statusCheckRollup") or [],
            )
        )
    return prs


def checks_have_passed(checks: list[dict]) -> bool:
    """Return True only if there is at least one check and every check succeeded.

    A PR with no checks at all is treated as not-yet-verified (returns False),
    since that usually means CI hasn't reported in yet rather than "nothing to
    check".
    """
    if not checks:
        return False
    for check in checks:
        conclusion = (check.get("conclusion") or "").upper()
        status = (check.get("status") or "").upper()
        if status and status != "COMPLETED":
            return False
        if conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            return False
    return True


def is_mergeable(pr: PullRequest) -> bool:
    """Return True if the PR has no real conflicts (being merely behind main is fine)."""
    if pr.mergeable is False:
        return False
    return pr.mergeable_state in MERGEABLE_STATES_OK_TO_MERGE or pr.mergeable_state == ""


def merge_and_delete(pr: PullRequest, dry_run: bool) -> None:
    """Merge a Dependabot PR (squash) and delete its head branch."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Merging PR #{pr.number} ({pr.title}) and deleting branch '{pr.head_ref_name}'")
    if dry_run:
        return

    if pr.head_ref_name in PROTECTED_BRANCHES:
        print(
            f"ERROR: refusing to delete protected branch '{pr.head_ref_name}' for PR #{pr.number}",
            file=sys.stderr,
        )
        return

    result = run_gh(["pr", "merge", str(pr.number), "--squash", "--delete-branch"])
    if result.returncode != 0:
        print(f"ERROR: failed to merge PR #{pr.number}: {result.stderr}", file=sys.stderr)


def process_pr(pr: PullRequest, dry_run: bool) -> None:
    """Decide whether a single Dependabot PR should be merged, and act on it."""
    if not checks_have_passed(pr.checks):
        print(f"SKIP: PR #{pr.number} ({pr.title}) -- checks not all passed")
        return
    if not is_mergeable(pr):
        print(
            f"SKIP: PR #{pr.number} ({pr.title}) -- not mergeable "
            f"(mergeable={pr.mergeable}, state={pr.mergeable_state})"
        )
        return
    merge_and_delete(pr, dry_run)


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
    args = parser.parse_args()
    dry_run = not args.yes

    print(f"INFO: Fetching open Dependabot PRs for {REPO_OWNER}/{REPO_NAME}...", file=sys.stderr)
    prs = fetch_open_dependabot_prs()
    print(f"INFO: {len(prs)} open Dependabot PR(s) found", file=sys.stderr)

    if dry_run:
        print("INFO: Running in dry-run mode. Pass --yes to actually merge/delete.", file=sys.stderr)

    for pr in prs:
        process_pr(pr, dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
