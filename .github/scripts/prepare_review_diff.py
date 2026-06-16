"""Prepare and safely truncate pull-request diffs for advisory AI reviews."""

from __future__ import annotations

import argparse
import subprocess
import sys

from review_common import MAX_DIFF_CHARS, format_truncation_log, prioritize_diff_blocks, truncate_diff

DEFAULT_GLOBS = ["*.py", "*.ts", "*.tsx", "*.js", "*.json", "*.md", "*.yaml", "*.yml", "Makefile", "*.mk", "*.sh", "*.ps1", "*.txt", "*.html", "*CODEOWNERS*", ]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for base ref and optional path globs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--pr-title", default="", help="PR title for prioritizing files")
    parser.add_argument("--issue-body", default="", help="Linked issue body for prioritizing files")
    parser.add_argument("paths", nargs="*", default=DEFAULT_GLOBS)
    return parser.parse_args()


def git_diff(base_ref: str, paths: list[str]) -> str:
    """Return the raw diff for the selected base ref and path filters."""
    result = subprocess.run(
        ["git", "diff", f"origin/{base_ref}...HEAD", "--", *paths],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> int:
    """Fetch the PR diff, prioritize by PR title/issue, truncate safely, and print to stdout."""
    args = parse_args()
    diff_text = git_diff(args.base_ref, args.paths)

    # Prioritize blocks so important files appear first in the truncated output
    prioritized_blocks = prioritize_diff_blocks(diff_text, args.pr_title, args.issue_body)
    prioritized_diff = "".join(prioritized_blocks)

    truncated_diff, was_truncated = truncate_diff(prioritized_diff, MAX_DIFF_CHARS)

    if was_truncated:
        # stderr is surfaced in the Actions log so maintainers know context was intentionally reduced.
        print(format_truncation_log(diff_text, truncated_diff), file=sys.stderr)

    sys.stdout.write(truncated_diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
