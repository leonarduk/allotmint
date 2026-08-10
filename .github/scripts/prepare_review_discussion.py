"""Prepare PR discussion since a provider's last review for advisory AI reviews."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time

MAX_DISCUSSION_CHARS = 20_000
TRUNCATION_NOTICE = "\n\n[discussion truncated to stay within the review budget]"
MAX_RATE_LIMIT_RETRIES = 5
RETRY_AFTER_PATTERN = re.compile(r"retry-after:\s*(\d+)", re.IGNORECASE)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments identifying the repo, PR, and reviewing provider."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--provider-name", required=True)
    parser.add_argument("--max-chars", type=int, default=MAX_DISCUSSION_CHARS)
    return parser.parse_args()


def _is_rate_limit_error(error: subprocess.CalledProcessError) -> bool:
    """Return whether ``gh api`` failed because GitHub rate-limited the request."""
    output = f"{error.stderr or ''}\n{error.stdout or ''}".lower()
    return any(marker in output for marker in ("http 403", "http 429", "status code 403", "status code 429"))


def _retry_delay(error: subprocess.CalledProcessError, retry_number: int) -> int:
    """Return GitHub's requested delay, or the exponential-backoff delay."""
    output = f"{error.stderr or ''}\n{error.stdout or ''}"
    retry_after = RETRY_AFTER_PATTERN.search(output)
    return int(retry_after.group(1)) if retry_after else 2 ** (retry_number - 1)


def _api_call_with_retry(path: str) -> subprocess.CompletedProcess[str]:
    """Call ``gh api``, retrying only GitHub rate-limit responses."""
    for retry_number in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return subprocess.run(
                ["gh", "api", path, "--paginate"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            if not _is_rate_limit_error(error) or retry_number == MAX_RATE_LIMIT_RETRIES:
                raise
            delay = _retry_delay(error, retry_number + 1)
            logger.warning(
                "Rate limited while fetching %s, retrying in %ss (attempt %s/%s)...",
                path,
                delay,
                retry_number + 1,
                MAX_RATE_LIMIT_RETRIES,
            )
            time.sleep(delay)
    raise AssertionError("retry loop exited unexpectedly")


def gh_api_list(path: str) -> list[dict]:
    """Return all paginated JSON objects for a ``gh api`` list endpoint."""
    result = _api_call_with_retry(path)
    items: list[dict] = []
    decoder = json.JSONDecoder()
    output = result.stdout
    position = 0
    while position < len(output):
        while position < len(output) and output[position].isspace():
            position += 1
        if position >= len(output):
            break
        page, position = decoder.raw_decode(output, position)
        items.extend(page)
    return items


def is_human_comment(comment: dict) -> bool:
    """Return True if a comment was posted by a human account."""
    user = comment.get("user") or {}
    return user.get("type") != "Bot"


def find_review_anchor(comments: list[dict], provider_name: str) -> str:
    """Return the timestamp of the provider's most recent posted review comment."""
    marker = f"## {provider_name} AI Code Review"
    timestamps = [
        comment["created_at"]
        for comment in comments
        if not is_human_comment(comment) and comment.get("body", "").startswith(marker)
    ]
    return max(timestamps, default="")


def format_comment(comment: dict, location: str) -> str:
    """Render a single comment as one discussion line."""
    author = (comment.get("user") or {}).get("login", "unknown")
    body = (comment.get("body") or "").strip()
    return f"[{comment['created_at']}] {author} ({location}): {body}"


def collect_discussion(repo: str, pr_number: str, provider_name: str, max_chars: int = MAX_DISCUSSION_CHARS) -> str:
    """Return formatted human discussion created after the provider's last review."""
    issue_comments = gh_api_list(f"repos/{repo}/issues/{pr_number}/comments")
    inline_comments = gh_api_list(f"repos/{repo}/pulls/{pr_number}/comments")
    anchor = find_review_anchor(issue_comments + inline_comments, provider_name)

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
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
