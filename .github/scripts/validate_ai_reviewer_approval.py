#!/usr/bin/env python3
"""Validate that Claude and GPT reviewers approved if they ran.

This script checks PR comments to determine if Claude and GPT reviews ran.
If they ran, they must contain an APPROVE verdict; if they didn't run, no approval is required.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import NamedTuple


class ReviewStatus(NamedTuple):
    """Status of a single AI reviewer."""

    ran: bool
    approved: bool


def get_pr_comments(pr_number: int) -> list[dict]:
    """Fetch all comments on a PR using GitHub CLI."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "comments"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return data.get("comments", [])


def check_claude_review(comments: list[dict]) -> ReviewStatus:
    """Check if Claude review ran and if it approved."""
    for comment in comments:
        body = comment.get("body", "")
        if "## Claude AI Code Review" in body:
            approved = "**APPROVE**" in body
            return ReviewStatus(ran=True, approved=approved)
    return ReviewStatus(ran=False, approved=False)


def check_gpt_review(comments: list[dict]) -> ReviewStatus:
    """Check if GPT review ran and if it approved."""
    for comment in comments:
        body = comment.get("body", "")
        if "## GPT AI Code Review" in body:
            approved = "**APPROVE**" in body
            return ReviewStatus(ran=True, approved=approved)
    return ReviewStatus(ran=False, approved=False)


def main() -> int:
    """Validate AI reviewer approvals."""
    try:
        pr_number = int(json.loads(subprocess.run(
            ["gh", "pr", "view", "--json", "number"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout).get("number", 0))
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
        print("ERROR: Could not determine PR number", file=sys.stderr)
        return 1

    try:
        comments = get_pr_comments(pr_number)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to fetch PR comments: {exc}", file=sys.stderr)
        return 1

    claude = check_claude_review(comments)
    gpt = check_gpt_review(comments)

    errors: list[str] = []

    if claude.ran and not claude.approved:
        errors.append("Claude review ran but did not APPROVE")
    if gpt.ran and not gpt.approved:
        errors.append("GPT review ran but did not APPROVE")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    status_parts = []
    if claude.ran:
        status_parts.append(f"Claude: APPROVED")
    if gpt.ran:
        status_parts.append(f"GPT: APPROVED")
    if not status_parts:
        status_parts.append("No AI reviews ran")

    print(f"✓ AI reviewer approval check passed: {'; '.join(status_parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
