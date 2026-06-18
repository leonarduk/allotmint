#!/usr/bin/env python3
"""Backward-compatible wrapper for publish_pr.py (moved to scripts/dev_tools/publish_pr.py)."""

import subprocess
import sys

if __name__ == "__main__":
    # Forward all arguments to the new location
    result = subprocess.run(
        [sys.executable, "scripts/dev_tools/publish_pr.py"] + sys.argv[1:],
        cwd=subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
    )
    sys.exit(result.returncode)
