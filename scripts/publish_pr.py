#!/usr/bin/env python3
"""Backward-compatible wrapper for publish_pr.py (moved to scripts/dev_tools/publish_pr.py)."""

import subprocess
import sys

if __name__ == "__main__":
    # Get git root directory
    try:
        git_root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_root = git_root_result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Error: Could not determine git root directory: {exc}", file=sys.stderr)
        sys.exit(1)

    # Forward all arguments to the new location
    result = subprocess.run(
        [sys.executable, "scripts/dev_tools/publish_pr.py"] + sys.argv[1:],
        cwd=git_root,
    )
    sys.exit(result.returncode)
