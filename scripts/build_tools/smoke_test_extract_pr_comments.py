#!/usr/bin/env python3
"""Smoke test for extract_pr_comments.py against a known, stable public PR.

Runs the real script end-to-end (subprocess, live GitHub API via `gh`) rather
than mocking it, to catch regressions in pagination, timestamp filtering, and
output shape that unit tests against internal functions would miss. Not part
of the default `pytest`/`make lint` run (see docs/CONTRIBUTING.md) since it
depends on network access and `gh` auth; run it explicitly with:

    make smoke-test-pr-comments
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# PR #4840 in this repo is merged (immutable comment history) and its
# top-level comments are all from bot accounts (chatgpt-codex-connector,
# github-actions), so there's no risk of a null `user` field from a deleted
# account — unlike octocat/Hello-World#1, whose review comments include a
# deleted-account commenter and crash extract_pr_comments.py's
# format_inline_comment() (a real bug, out of scope for this smoke test per
# #4531's constraints). --since predates the repo's creation so every
# comment on the PR is included regardless of when its head commit landed.
REPO = "leonarduk/allotmint"
PR_NUMBER = "4840"
SINCE = "2011-01-01T00:00:00Z"
REQUIRED_FIELDS = ("id", "created_at", "body", "type")

SCRIPT_PATH = Path(__file__).parent / "extract_pr_comments.py"


def run_extract_pr_comments() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--pr",
            PR_NUMBER,
            "--repo",
            REPO,
            "--since",
            SINCE,
            "--format",
            "jsonl",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


def parse_jsonl(stdout: str) -> list[dict]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError("Expected non-empty JSONL output, got none")
    return [json.loads(line) for line in lines]


def check_required_fields(comments: list[dict]) -> None:
    for comment in comments:
        missing = [field for field in REQUIRED_FIELDS if field not in comment]
        if missing:
            raise AssertionError(f"Comment {comment.get('id')} missing field(s): {missing}")


def check_ascending_order(comments: list[dict]) -> None:
    timestamps = [c["created_at"] for c in comments]
    if timestamps != sorted(timestamps):
        raise AssertionError("Comments are not sorted by created_at ascending")


def main() -> int:
    result = run_extract_pr_comments()
    if result.returncode != 0:
        print(
            f"FAIL: extract_pr_comments.py exited {result.returncode}\n" f"stderr:\n{result.stderr}",
            file=sys.stderr,
        )
        return 1

    try:
        comments = parse_jsonl(result.stdout)
        check_required_fields(comments)
        check_ascending_order(comments)
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"PASS: {len(comments)} comment(s) fetched from {REPO}#{PR_NUMBER}, all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
