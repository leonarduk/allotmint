#!/usr/bin/env python3
"""Check the real GitHub Actions run status for the current branch/PR.

Complements g_run_ci_checks.py, which mirrors credential-free workflow steps
locally: this script talks to the actual GitHub Actions API (via `gh`) so you
can see whether the real CI run for your pushed branch has started, is still
running, or has failed -- and jump straight to the failed logs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def run_gh(args: list[str]) -> str:
    """Run a `gh` subcommand and return its stdout, raising on failure."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise SystemExit(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def current_branch() -> str:
    """Return the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def local_head_sha() -> str:
    """Return the local HEAD commit SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def pr_head_sha(branch: str) -> str | None:
    """Return the PR head SHA for `branch`, or None if there is no open PR."""
    result = subprocess.run(
        ["gh", "pr", "view", branch, "--json", "headRefOid"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return None
    return json.loads(result.stdout)["headRefOid"]


def fetch_runs(branch: str, limit: int = 50) -> list[dict]:
    """Fetch recent Actions runs for `branch`."""
    output = run_gh(
        [
            "run",
            "list",
            "--branch",
            branch,
            "--limit",
            str(limit),
            "--json",
            "databaseId,name,status,conclusion,headSha,url",
        ]
    )
    return json.loads(output)


def filter_to_sha(runs: list[dict], sha: str) -> list[dict]:
    """Keep only runs whose headSha matches `sha`.

    A green run on an older SHA does not satisfy a required-checks gate, so
    checks must be matched to the current head SHA rather than just the
    branch name (see docs/CONTRIBUTING.md CI guidance).
    """
    return [run for run in runs if run["headSha"] == sha]


def format_runs(runs: list[dict]) -> str:
    """Render one status line per run."""
    lines = []
    for run in runs:
        status = run["conclusion"] or run["status"]
        lines.append(f"[{run['databaseId']}] {run['name']}: {status}  {run['url']}")
    return "\n".join(lines)


def watch_run(run_id: str) -> int:
    """Watch a run until it completes, returning its exit status."""
    result = subprocess.run(["gh", "run", "watch", run_id, "--exit-status"], check=False)
    return result.returncode


def view_failed_log(run_id: str) -> None:
    """Print the failed-step logs for a run."""
    subprocess.run(["gh", "run", "view", run_id, "--log-failed"], check=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", help="branch to check (default: current branch)")
    parser.add_argument("--watch", metavar="RUN_ID", help="watch a specific run until it completes")
    parser.add_argument("--log-failed", metavar="RUN_ID", help="show failed-step logs for a run")
    parser.add_argument(
        "--all-shas",
        action="store_true",
        help="show every recent run for the branch instead of only the current head SHA",
    )
    return parser.parse_args(argv)


def prompt_for_action(runs: list[dict]) -> int:
    """Ask an interactive user whether to watch a run or view failed logs."""
    if not sys.stdin.isatty() or not runs:
        return 0
    answer = input(
        "\nEnter a run ID to watch, 'f<run_id>' to view failed logs, or press Enter to exit: "
    ).strip()
    if not answer:
        return 0
    if answer.startswith("f"):
        view_failed_log(answer[1:])
        return 0
    return watch_run(answer)


def main(argv: list[str] | None = None) -> int:
    """Provide the CLI entry point."""
    args = parse_args(argv)
    if args.watch:
        return watch_run(args.watch)
    if args.log_failed:
        view_failed_log(args.log_failed)
        return 0

    branch = args.branch or current_branch()
    sha = pr_head_sha(branch) or local_head_sha()
    runs = fetch_runs(branch)
    if not args.all_shas:
        runs = filter_to_sha(runs, sha)

    print(f"Branch: {branch}  HEAD SHA: {sha[:12]}")
    if not runs:
        print(
            "No GitHub Actions runs found for this SHA yet. "
            "CI may not have started -- wait and retry."
        )
    else:
        print(format_runs(runs))

    return prompt_for_action(runs)


if __name__ == "__main__":
    raise SystemExit(main())
