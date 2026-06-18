#!/usr/bin/env python3
"""Extract PR comments added since last commit in LLM-friendly format."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

script_dir = Path(__file__).parent
spec = importlib.util.spec_from_file_location("comment_formats", script_dir / "comment_formats.py")
comment_formats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comment_formats)
to_fixer = comment_formats.to_fixer
to_jsonl = comment_formats.to_jsonl


def run_gh_command(args: list[str], json_output: bool = False) -> tuple[str, int]:
    """Run a gh command and return output, exit code."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        return result.stdout.strip(), result.returncode
    except FileNotFoundError:
        print("Error: 'gh' CLI not found. Install GitHub CLI.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: 'gh' command timed out.", file=sys.stderr)
        sys.exit(1)


def infer_repo() -> tuple[str, str]:
    """Infer owner/repo from git remote."""
    output, code = run_gh_command(["repo", "view", "--json", "owner,name"])
    if code != 0:
        print(
            "Error: Could not infer repo from git remote. "
            "Check that: (1) you are in a git repository with a remote, "
            "(2) GitHub CLI is authenticated (run 'gh auth login').",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        data = json.loads(output)
        owner = data.get("owner", {}).get("login")
        repo = data.get("name")
        if not owner or not repo:
            raise ValueError("Missing owner or name in response")
        return owner, repo
    except (json.JSONDecodeError, ValueError):
        print("Error: Could not parse owner/name from gh repo view.", file=sys.stderr)
        sys.exit(1)


def get_commit_date(owner: str, repo: str, sha: str) -> str:
    """Get the committer date of a commit by SHA."""
    args = [
        "api",
        f"/repos/{owner}/{repo}/commits/{sha}",
        "--jq",
        ".commit.committer.date",
    ]
    date_str, code = run_gh_command(args)
    if code != 0:
        print(f"Error: Could not fetch commit {sha}.", file=sys.stderr)
        sys.exit(1)
    return date_str.strip()


def get_pr_head_commit_date(owner: str, repo: str, pr: int) -> str:
    """Get the committer date of the PR's head commit."""
    args = [
        "api",
        f"/repos/{owner}/{repo}/pulls/{pr}",
        "--jq",
        ".head.sha",
    ]
    sha, code = run_gh_command(args)
    if code != 0:
        print(f"Error: Could not fetch PR {pr}.", file=sys.stderr)
        sys.exit(1)
    return get_commit_date(owner, repo, sha.strip())


def fetch_paginated(owner: str, repo: str, endpoint: str) -> list[dict[str, Any]]:
    """Fetch paginated API endpoint, return all items."""
    items: list[dict[str, Any]] = []
    page = 1

    while True:
        args = [
            "api",
            f"{endpoint}?per_page=100&page={page}",
        ]
        output, code = run_gh_command(args)
        if code != 0:
            if items:
                print(
                    f"Warning: API request to {endpoint} page {page} failed after "
                    f"collecting {len(items)} items. Returning partial results.",
                    file=sys.stderr,
                )
                return items
            print(f"Error: API request to {endpoint} page {page} failed.", file=sys.stderr)
            return []

        try:
            data = json.loads(output) if output else []
        except json.JSONDecodeError:
            print(f"Error: Failed to parse JSON from {endpoint} page {page}.", file=sys.stderr)
            return items

        if not isinstance(data, list) or len(data) == 0:
            break

        items.extend(data)
        page += 1

    return items


def fetch_reviews(owner: str, repo: str, pr: int) -> dict[int, bool]:
    """Fetch reviews and map review_id -> is_currently_dismissed (resolved)."""
    endpoint = f"/repos/{owner}/{repo}/pulls/{pr}/reviews"
    reviews = fetch_paginated(owner, repo, endpoint)
    review_dismissed: dict[int, bool] = {}

    if not reviews:
        print(
            "Warning: No reviews found. The 'resolved' field for inline comments "
            "will default to false. This may indicate an API error.",
            file=sys.stderr,
        )
        return review_dismissed

    for review in reviews:
        if isinstance(review, dict):
            review_id = review.get("id")
            state = review.get("state", "")
            is_dismissed = state == "DISMISSED"
            if review_id is not None:
                review_dismissed[review_id] = is_dismissed

    return review_dismissed


def fetch_inline_comments(owner: str, repo: str, pr: int) -> list[dict[str, Any]]:
    """Fetch inline review thread comments."""
    endpoint = f"/repos/{owner}/{repo}/pulls/{pr}/comments"
    return fetch_paginated(owner, repo, endpoint)


def fetch_top_level_comments(owner: str, repo: str, pr: int) -> list[dict[str, Any]]:
    """Fetch top-level issue/PR comments."""
    endpoint = f"/repos/{owner}/{repo}/issues/{pr}/comments"
    return fetch_paginated(owner, repo, endpoint)


def parse_iso_datetime(iso_str: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def filter_by_timestamp(
    items: list[dict[str, Any]], since_timestamp: datetime
) -> list[dict[str, Any]]:
    """Filter items where created_at > since_timestamp (strictly after)."""
    filtered = []
    for item in items:
        created_at_str = item.get("created_at")
        if created_at_str:
            created_at = parse_iso_datetime(created_at_str)
            if created_at > since_timestamp:
                filtered.append(item)
    return filtered


def format_inline_comment(
    comment: dict[str, Any], review_dismissed: dict[int, bool]
) -> dict[str, Any]:
    """Format inline comment for JSONL output."""
    review_id = comment.get("pull_request_review_id")
    resolved = review_dismissed.get(review_id, False) if review_id is not None else False

    return {
        "id": comment.get("id"),
        "author": comment.get("user", {}).get("login"),
        "type": "inline",
        "path": comment.get("path"),
        "line": comment.get("line"),
        "created_at": comment.get("created_at"),
        "body": comment.get("body"),
        "resolved": resolved,
    }


def format_top_level_comment(comment: dict[str, Any]) -> dict[str, Any]:
    """Format top-level comment for JSONL output."""
    return {
        "id": comment.get("id"),
        "author": comment.get("user", {}).get("login"),
        "type": "top-level",
        "created_at": comment.get("created_at"),
        "body": comment.get("body"),
    }


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(description="Extract PR comments in LLM-friendly format.")
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--repo", help="Owner/repo (inferred from git remote if not provided)")
    parser.add_argument(
        "--since", help="Override since boundary (SHA or ISO datetime)"
    )
    parser.add_argument(
        "--skip-resolved",
        action="store_true",
        help="Omit resolved inline thread comments",
    )
    parser.add_argument(
        "--format",
        choices=["fixer", "jsonl"],
        default="fixer",
        help="Output format: fixer (compact, default) or jsonl (line-delimited JSON)",
    )
    parser.add_argument(
        "--output", help="Output file (defaults to stdout)"
    )
    return parser.parse_args()


def determine_since_timestamp(args: argparse.Namespace, owner: str, repo: str) -> datetime:
    """Determine the since timestamp from args (SHA or ISO datetime) or PR head commit."""
    if args.since:
        try:
            return parse_iso_datetime(args.since)
        except ValueError:
            since_date_str = get_commit_date(owner, repo, args.since)
            return parse_iso_datetime(since_date_str)
    since_str = get_pr_head_commit_date(owner, repo, args.pr)
    return parse_iso_datetime(since_str)


def process_comments(
    owner: str,
    repo: str,
    pr_number: int,
    since_timestamp: datetime,
    skip_resolved: bool,
) -> list[dict[str, Any]]:
    """Fetch, filter, and deduplicate comments."""
    review_dismissed = fetch_reviews(owner, repo, pr_number)
    inline_comments = fetch_inline_comments(owner, repo, pr_number)
    top_level_comments = fetch_top_level_comments(owner, repo, pr_number)

    inline_comments = filter_by_timestamp(inline_comments, since_timestamp)
    top_level_comments = filter_by_timestamp(top_level_comments, since_timestamp)

    formatted_inline = [
        format_inline_comment(c, review_dismissed) for c in inline_comments
    ]
    formatted_top_level = [format_top_level_comment(c) for c in top_level_comments]

    if skip_resolved:
        formatted_inline = [c for c in formatted_inline if not c.get("resolved")]

    all_comments = formatted_inline + formatted_top_level

    seen_ids: set[int | None] = set()
    deduped = []
    for comment in sorted(all_comments, key=lambda c: c.get("created_at", "")):
        comment_id = comment.get("id")
        if comment_id not in seen_ids:
            deduped.append(comment)
            seen_ids.add(comment_id)

    return deduped


def write_output(
    comments: list[dict[str, Any]], output_file: str | None, format_type: str
) -> int:
    """Write comments to output file or stdout in the specified format."""
    formatter = to_fixer if format_type == "fixer" else to_jsonl
    try:
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                for line in formatter(comments):
                    f.write(line + "\n")
        else:
            for line in formatter(comments):
                print(line)
    except OSError as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.repo:
        owner, repo = args.repo.split("/", 1)
    else:
        owner, repo = infer_repo()

    since_timestamp = determine_since_timestamp(args, owner, repo)
    deduped = process_comments(owner, repo, args.pr, since_timestamp, args.skip_resolved)

    if not deduped:
        print(
            f"No comments found for PR {args.pr} after {since_timestamp.isoformat()}.",
            file=sys.stderr,
        )
        return 0

    return write_output(deduped, args.output, args.format)


if __name__ == "__main__":
    raise SystemExit(main())
