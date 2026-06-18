#!/usr/bin/env python3
"""Sync GitHub issues to local markdown files for offline access."""

import os
import re
import subprocess
import sys
from pathlib import Path

import requests

REPO_OWNER = "leonarduk"
REPO_NAME = "allotmint"
ISSUES_DIR = Path(__file__).parent.parent.parent / "issues"
GITHUB_API_BASE = "https://api.github.com"


def get_github_token():
    """Get GitHub token from env var or gh CLI."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("Error: GITHUB_TOKEN env var not set and 'gh auth token' failed.", file=sys.stderr)
    sys.exit(1)


def slugify(title):
    """Convert title to slug: lowercase, non-alphanumeric -> hyphen, max 60 chars."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


def make_filename(issue_id, title):
    """Create filename as {id}_{slug}.md."""
    slug = slugify(title)
    return f"{issue_id}_{slug}.md"


def fetch_issues(token, state):
    """Fetch all issues (open or closed) with pagination."""
    issues = []
    page = 1
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    while True:
        url = (
            f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/issues"
            f"?state={state}&per_page=100&page={page}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=10)
        except requests.RequestException as e:
            print(f"Error fetching issues: {e}", file=sys.stderr)
            return issues

        if resp.status_code in (403, 429):
            reset_time = resp.headers.get("X-RateLimit-Reset", "unknown")
            print(
                f"Warning: GitHub API rate limit exceeded. Reset at {reset_time}. "
                f"Writing {len(issues)} issues fetched so far.",
                file=sys.stderr,
            )
            return issues

        if resp.status_code != 200:
            print(f"Error: API returned {resp.status_code}", file=sys.stderr)
            return issues

        try:
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            print("Error: Failed to parse JSON from API response", file=sys.stderr)
            return issues

        if not data:
            break

        for item in data:
            if "pull_request" not in item:
                issues.append(item)

        page += 1

    return issues


def format_issue_file(issue):
    """Format issue as markdown with header block."""
    issue_id = issue["number"]
    title = issue["title"]
    url = issue["html_url"]
    labels = ", ".join([label["name"] for label in issue["labels"]])
    state = issue["state"]
    body = issue["body"] or ""

    lines = [
        f"# {issue_id} — {title}",
        "",
        f"**URL:** {url}",
        f"**Labels:** {labels}",
        f"**State:** {state}",
        "",
        body,
    ]
    return "\n".join(lines)


def main():
    """Main sync logic."""
    token = get_github_token()
    ISSUES_DIR.mkdir(exist_ok=True)

    open_issues = fetch_issues(token, "open")
    closed_issues = fetch_issues(token, "closed")

    closed_ids = {issue["number"] for issue in closed_issues}
    open_ids_to_filenames = {}

    for issue in open_issues:
        issue_id = issue["number"]
        filename = make_filename(issue_id, issue["title"])
        filepath = ISSUES_DIR / filename
        content = format_issue_file(issue)
        open_ids_to_filenames[issue_id] = filename

        if filepath.exists():
            with open(filepath, encoding="utf-8") as f:
                existing = f.read()
            if existing == content:
                continue

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    # Remove files that are:
    # 1. For closed issues, or
    # 2. For open issues but with outdated filenames (e.g., issue was renamed)
    for filepath in ISSUES_DIR.glob("*.md"):
        match = re.match(r"^(\d+)_", filepath.name)
        if not match:
            continue
        issue_id = int(match.group(1))
        is_closed = issue_id in closed_ids
        current_name = open_ids_to_filenames.get(issue_id)
        is_outdated = current_name and current_name != filepath.name
        if is_closed or is_outdated:
            filepath.unlink()

    print(f"Synced {len(open_issues)} open issues to {ISSUES_DIR}")


if __name__ == "__main__":
    main()
