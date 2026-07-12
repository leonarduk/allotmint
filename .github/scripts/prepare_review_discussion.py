"""Prepare PR discussion since a provider's last review for advisory AI reviews.

Fetches both inline review-thread comments (`pulls/{n}/comments`) and top-level
conversation comments (`issues/{n}/comments`) via `gh api`, filters out bots and
the reviewing provider's own prior review bodies, anchors the window to the
provider's last posted review comment, and prints the remaining human discussion
sorted by creation time.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

MAX_DISCUSSION_CHARS = 20_000
TRUNCATION_NOTICE = "\n\n[discussion truncated to stay within the review budget]"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments identifying the repo, PR, and reviewing provider."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--provider-name", required=True)
    parser.add_argument("--max-chars", type=int, default=MAX_DISCUSSION_CHARS)
    return parser.parse_args()


def gh_api_list(path: str) -> list[dict]:
    """Return all paginated JSON objects for a `gh api` list endpoint."""
    result = subprocess.run(
        ["gh", "api", path, "--paginate"],
        check=True,
        capture_output=True,
        text=True,
    )
    items: list[dict] = []
    decoder = json.JSONDecoder()
    text = result.stdout
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        page, end = decoder.raw_decode(text, pos)
        items.extend(page)
        pos = end
    return items


def is_human_comment(comment: dict) -> bool:
    """Return True if a comment was posted by a human account."""
    user = comment.get("user") or {}
    return user.get("type") != "Bot"


def find_review_anchor(issue_comments: list[dict], provider_name: str) -> str:
    """Return the timestamp of the provider's most recent posted review comment.

    Returns an empty string if no prior review comment exists, meaning the full
    discussion history should be included.
    """
    marker = f"## {provider_name} AI Code Review"
    timestamps = [
        comment["created_at"]
        for comment in issue_comments
        if not is_human_comment(comment) and comment.get("body", "").startswith(marker)
    ]
    return max(timestamps, default="")


def format_comment(comment: dict, location: str) -> str:
    """Render a single comment as one discussion line."""
    author = (comment.get("user") or {}).get("login", "unknown")
    body = (comment.get("body") or "").strip()
    return f"[{comment['created_at']}] {author} ({location}): {body}"


def collect_discussion(
    repo: str, pr_number: str, provider_name: str, max_chars: int = MAX_DISCUSSION_CHARS
) -> str:
    """Return formatted human discussion created after the provider's last review."""
    issue_comments = gh_api_list(f"repos/{repo}/issues/{pr_number}/comments")
    inline_comments = gh_api_list(f"repos/{repo}/pulls/{pr_number}/comments")

    anchor = find_review_anchor(issue_comments, provider_name)

    entries: list[tuple[str, str]] = []
    for comment in issue_comments:
        if is_human_comment(comment) and comment["created_at"] > anchor:
            entries.append((comment["created_at"], format_comment(comment, "conversation")))
    for comment in inline_comments:
        if is_human_comment(comment) and comment["created_at"] > anchor:
            location = f"inline on {comment.get('path', 'unknown file')}"
            entries.append((comment["created_at"], format_comment(comment, location)))

    entries.sort(key=lambda entry: entry[0])
    discussion = "\n\n".join(text for _, text in entries)

    if len(discussion) > max_chars:
        cut = discussion[: max_chars - len(TRUNCATION_NOTICE)]
        discussion = cut.rsplit("\n\n", 1)[0] + TRUNCATION_NOTICE

    return discussion


def main() -> int:
    """Fetch and print PR discussion since the provider's last review."""
    args = parse_args()
    discussion = collect_discussion(args.repo, args.pr_number, args.provider_name, args.max_chars)
    sys.stdout.write(discussion)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
