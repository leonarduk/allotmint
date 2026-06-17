"""CLI helper to create a GitHub issue checkout branch and file."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import requests


def get_repo_info() -> tuple[str, str]:
    """Extract owner and repo from git remote origin."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        # Handle both https and ssh URLs
        if url.startswith("git@"):
            # git@github.com:owner/repo.git
            match = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", url)
        else:
            # https://github.com/owner/repo.git
            match = re.search(r"github\.com/([^/]+)/(.+?)(?:\.git)?$", url)
        if match:
            return match.group(1), match.group(2).replace(".git", "")
    except subprocess.CalledProcessError:
        pass
    raise ValueError("Could not determine GitHub repo from git remote origin")


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")[:50]


def fetch_issue(owner: str, repo: str, issue_id: int) -> dict:
    """Fetch issue details from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_id}"
    resp = requests.get(url, timeout=10)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
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
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        result = subprocess.run(
            ["git", "rev-parse", "origin/master"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Failed to get main branch SHA: {exc}", file=sys.stderr)
        sys.exit(1)


def create_branch(
    owner: str, repo: str, branch_name: str, sha: str, token: str | None = None
) -> None:
    """Create a branch in the remote repo."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    data = {"ref": f"refs/heads/{branch_name}", "sha": sha}
    resp = requests.post(url, json=data, headers=headers, timeout=10)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if resp.status_code == 422:
            # Branch already exists
            print(f"Branch {branch_name} already exists (will proceed with checkout)", file=sys.stderr)
        else:
            print(f"Failed to create branch: {exc}", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a GitHub issue checkout branch")
    parser.add_argument("issue_id", type=int, help="GitHub issue ID")
    parser.add_argument(
        "--token",
        help="GitHub personal access token (for creating branches)",
        default=None,
    )
    args = parser.parse_args()

    # Get repo info
    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Using repository: {owner}/{repo}")

    # Fetch issue
    print(f"Fetching issue #{args.issue_id}...")
    issue = fetch_issue(owner, repo, args.issue_id)
    title = issue["title"]
    body = issue["body"] or ""

    # Create branch name
    slug = slugify(title)
    branch_name = f"fix/issue-{args.issue_id}-{slug}"
    print(f"Branch name: {branch_name}")

    # Get the current main/master branch SHA
    print("Getting main branch SHA...")
    sha = get_main_branch_sha(owner, repo)

    # Create branch in remote
    print("Creating branch in remote...")
    create_branch(owner, repo, branch_name, sha, args.token or os.getenv("GITHUB_TOKEN"))

    # Fetch and checkout
    print("Fetching from origin...")
    try:
        subprocess.run(["git", "fetch", "origin"], check=True)
        print(f"Checking out {branch_name}...")
        subprocess.run(["git", "checkout", branch_name], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to checkout branch: {exc}", file=sys.stderr)
        sys.exit(1)

    # Write issue to markdown file
    issue_file = Path(f".issue-{args.issue_id}.md")
    content = f"# {title}\n\n{body}\n"
    issue_file.write_text(content)
    print(f"Wrote issue to {issue_file}")
    print(f"\n[OK] Ready to work on issue #{args.issue_id}")


if __name__ == "__main__":
    main()
