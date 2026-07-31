"""CLI helper to check out the branch for an open GitHub pull request."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import requests
from lib.github_repo import get_repo_info


def _auth_headers(token: str | None) -> dict:
    """Build GitHub API headers, including authentication when available."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def list_open_prs(owner: str, repo: str, token: str | None) -> list[dict]:
    """Fetch open pull requests from the GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    try:
        resp = requests.get(
            url,
            headers=_auth_headers(token),
            params={"state": "open", "per_page": 100},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Failed to list open pull requests: {exc}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def fetch_pr(owner: str, repo: str, pr_number: int, token: str | None) -> dict:
    """Fetch a single pull request from the GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    try:
        resp = requests.get(url, headers=_auth_headers(token), timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Failed to fetch PR #{pr_number}: {exc}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def prompt_for_pr(prs: list[dict]) -> dict:
    """List open PRs and prompt the user to pick one."""
    if not prs:
        print("No open pull requests found.", file=sys.stderr)
        sys.exit(1)

    print("Open pull requests:")
    for pr in prs:
        author = (pr.get("user") or {}).get("login", "unknown")
        print(f"  #{pr['number']}: {pr['title']} [{pr['head']['ref']}] (by {author})")

    try:
        choice = input("\nEnter PR number to work on: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
    try:
        pr_number = int(choice)
    except ValueError:
        print(f"Invalid PR number: {choice!r}", file=sys.stderr)
        sys.exit(1)

    for pr in prs:
        if pr["number"] == pr_number:
            return pr
    print(f"PR #{pr_number} not found among open pull requests.", file=sys.stderr)
    sys.exit(1)


def checkout_pr_branch(pr: dict) -> None:
    """Fetch and check out the branch a PR is built on, handling forks."""
    head = pr["head"]
    branch_name = head["ref"]
    head_repo = head.get("repo")
    base_repo_full_name = pr["base"]["repo"]["full_name"]
    is_fork = head_repo is None or head_repo.get("full_name") != base_repo_full_name

    if is_fork:
        if head_repo is None:
            print(
                "Error: PR head repository is inaccessible (likely deleted fork); cannot check out.",
                file=sys.stderr,
            )
            sys.exit(1)
        fork_full_name = head_repo["full_name"]
        fork_clone_url = head_repo["clone_url"]
        remote_name = f"pr-{pr['number']}"
        local_branch = f"pr-{pr['number']}-{branch_name}"
        remote_ref = f"{remote_name}/{branch_name}"
        print(f"PR head is in fork {fork_full_name}; fetching as remote '{remote_name}'...")
        subprocess.run(["git", "remote", "remove", remote_name], capture_output=True, check=False)
        try:
            subprocess.run(["git", "remote", "add", remote_name, fork_clone_url], check=True)
            subprocess.run(["git", "fetch", remote_name, branch_name], check=True)
        except subprocess.CalledProcessError as exc:
            print(f"Failed to fetch {branch_name} from fork {fork_full_name}: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            _checkout_local_branch(local_branch, remote_ref)
        finally:
            # The remote is temporary and must also be removed after a failed checkout.
            subprocess.run(["git", "remote", "remove", remote_name], capture_output=True, check=False)
        return

    print(f"Fetching branch {branch_name} from origin...")
    try:
        subprocess.run(["git", "fetch", "origin", branch_name], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to fetch branch {branch_name} from origin: {exc}", file=sys.stderr)
        sys.exit(1)
    _checkout_local_branch(branch_name, f"origin/{branch_name}")


def _checkout_local_branch(local_branch: str, remote_ref: str) -> None:
    """Check out ``local_branch`` tracking ``remote_ref``, updating it in place if it already exists."""
    try:
        subprocess.run(
            ["git", "checkout", "-b", local_branch, remote_ref],
            check=True,
            capture_output=True,
        )
        return
    except subprocess.CalledProcessError:
        pass

    try:
        subprocess.run(["git", "checkout", local_branch], check=True)
        subprocess.run(["git", "merge", "--ff-only", remote_ref], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to update local branch {local_branch} to {remote_ref}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Fetch a selected pull request and check out its head branch."""
    parser = argparse.ArgumentParser(description="Check out the branch for an open GitHub pull request")
    parser.add_argument(
        "pr_number",
        type=int,
        nargs="?",
        default=None,
        help="GitHub PR number (omit to list open PRs and choose interactively)",
    )
    parser.add_argument(
        "--token",
        help="GitHub personal access token (also reads GITHUB_TOKEN env var)",
        default=None,
    )
    args = parser.parse_args()

    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Using repository: {owner}/{repo}")
    token = args.token or os.getenv("GITHUB_TOKEN")

    print("Fetching from origin...")
    try:
        subprocess.run(["git", "fetch", "origin"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to fetch from origin: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.pr_number is not None:
        pr = fetch_pr(owner, repo, args.pr_number, token)
        if pr.get("state") != "open":
            print(f"Warning: PR #{args.pr_number} is {pr.get('state')}, not open.", file=sys.stderr)
    else:
        prs = list_open_prs(owner, repo, token)
        pr = prompt_for_pr(prs)

    print(f"\nWorking on PR #{pr['number']}: {pr['title']}")
    checkout_pr_branch(pr)
    print(f"\n[OK] Checked out branch for PR #{pr['number']}")


if __name__ == "__main__":
    main()
