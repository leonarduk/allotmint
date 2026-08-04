"""CLI helper to create a GitHub issue checkout branch and file."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from lib.github_repo import get_repo_info


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Falls back to a deterministic hash when the title has no ASCII
    word characters (e.g. emoji-only titles), so branch names never end up
    with a trailing hyphen like ``fix/issue-4445-``.
    """
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    slug = slug.strip("-")[:50]
    if not slug:
        slug = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return slug


def fetch_issue(owner: str, repo: str, issue_id: int, token: str | None = None) -> dict:
    """Fetch issue details from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_id}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Failed to fetch issue #{issue_id}: {exc}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def get_main_branch_sha(owner: str, repo: str) -> str:
    """Get the SHA of the main/master branch."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        result = subprocess.run(
            ["git", "rev-parse", "origin/master"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Failed to get main branch SHA: {exc}", file=sys.stderr)
        sys.exit(1)


def create_branch(owner: str, repo: str, branch_name: str, sha: str, token: str | None = None) -> None:
    """Create a branch in the remote repo."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    data = {"ref": f"refs/heads/{branch_name}", "sha": sha}
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if resp.status_code == 422 and "Reference already exists" in resp.text:
            print(f"Branch {branch_name} already exists (will proceed with checkout)", file=sys.stderr)
        else:
            print(f"Failed to create branch: {exc}", file=sys.stderr)
            sys.exit(1)
    except requests.RequestException as exc:
        print(f"Failed to create branch: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Create and check out a remote branch for the requested issue."""
    parser = argparse.ArgumentParser(description="Create a GitHub issue checkout branch")
    parser.add_argument("issue_id", type=int, help="GitHub issue ID")
    parser.add_argument(
        "--token",
        help="GitHub personal access token (for creating branches)",
        default=None,
    )
    parser.add_argument(
        "--type",
        choices=["fix", "feat"],
        default="fix",
        help="Branch prefix to use (default: fix)",
    )
    args = parser.parse_args()

    # Get repo info
    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Using repository: {owner}/{repo}")

    # Fetch latest refs before resolving SHAs
    print("Fetching from origin...")
    try:
        subprocess.run(["git", "fetch", "origin"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to fetch from origin: {exc}", file=sys.stderr)
        sys.exit(1)

    token = args.token or os.getenv("GITHUB_TOKEN")

    # Fetch issue
    print(f"Fetching issue #{args.issue_id}...")
    issue = fetch_issue(owner, repo, args.issue_id, token)
    title = issue.get("title", "")
    body = issue.get("body") or ""
    if not title:
        print(f"Error: Issue #{args.issue_id} has no title", file=sys.stderr)
        sys.exit(1)

    # Create branch name
    slug = slugify(title)
    branch_name = f"{args.type}/issue-{args.issue_id}-{slug}"
    print(f"Branch name: {branch_name}")

    # Get the current main/master branch SHA
    print("Getting main branch SHA...")
    sha = get_main_branch_sha(owner, repo)

    # Create branch in remote
    print("Creating branch in remote...")
    create_branch(owner, repo, branch_name, sha, token)

    # Small delay to avoid a race where the branch ref isn't visible yet
    time.sleep(1)

    # Fetch the newly created branch so the local checkout can reference it
    try:
        subprocess.run(["git", "fetch", "origin", branch_name], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        # Fallback: fetch all refs if specific branch fetch fails
        subprocess.run(["git", "fetch", "origin"], check=True)

    # Checkout the new branch (create local tracking branch if needed)
    try:
        print(f"Checking out {branch_name}...")
        subprocess.run(
            ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        # Branch might already exist locally; try simple checkout
        try:
            subprocess.run(["git", "checkout", branch_name], check=True)
        except subprocess.CalledProcessError as exc:
            print(f"Failed to checkout branch: {exc}", file=sys.stderr)
            sys.exit(1)

    # Write issue to markdown file (preserve original content without reformatting)
    issue_file = Path(f".issue-{args.issue_id}.md")
    content = f"{title}\n\n{body}\n"
    issue_file.write_text(content, encoding="utf-8")
    print(f"Wrote issue to {issue_file}")
    print(f"\n[OK] Ready to work on issue #{args.issue_id}")


if __name__ == "__main__":
    main()
