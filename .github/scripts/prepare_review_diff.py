"""Prepare and safely truncate pull-request diffs for advisory AI reviews."""

from __future__ import annotations

import argparse
import subprocess
import sys

from review_common import MAX_DIFF_CHARS, format_truncation_log, truncate_diff

DEFAULT_GLOBS = ["*.py", "*.ts", "*.tsx", "*.js", "*.json", "*.md", "*.yaml", "*.yml"]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for base ref and optional path globs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
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
    """Fetch the PR diff, truncate it safely, and print it to stdout for GITHUB_OUTPUT."""
    args = parse_args()
    diff_text = git_diff(args.base_ref, args.paths)
    truncated_diff, was_truncated = truncate_diff(diff_text, MAX_DIFF_CHARS)

    if was_truncated:
        # stderr is surfaced in the Actions log so maintainers know context was intentionally reduced.
        print(format_truncation_log(diff_text, truncated_diff), file=sys.stderr)

    sys.stdout.write(truncated_diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
