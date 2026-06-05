"""Create follow-up GitHub issues idempotently from a JSON list of titles."""

from __future__ import annotations

import json
import subprocess
import sys


def issue_exists(title: str) -> bool:
    """Return True if an ai-suggested issue with this exact title already exists."""
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", "ai-suggested",
            "--search", title,
            "--json", "title",
            "--limit", "20",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return any(i.get("title", "").strip() == title.strip() for i in issues)


def create_issues(titles: list[str], pr_number: str) -> None:
    for title in titles:
        if not title:
            continue
        if issue_exists(title):
            print(f"Skipping (already exists): {title}")
            continue
        print(f"Creating issue: {title}")
        subprocess.run(
            [
                "gh", "issue", "create",
                "--title", title,
                "--body", f"Follow-up suggested by Claude AI review of PR #{pr_number}.",
                "--label", "ai-suggested",
            ],
            check=True,
        )


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <followups_json_file> <pr_number>", file=sys.stderr)
        return 1
    followups_file, pr_number = sys.argv[1], sys.argv[2]
    try:
        with open(followups_file) as f:
            titles = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR reading {followups_file}: {exc}", file=sys.stderr)
        return 1
    create_issues(titles, pr_number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
