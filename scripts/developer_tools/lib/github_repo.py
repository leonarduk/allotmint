"""Helpers for identifying the GitHub repository in the current checkout."""

from __future__ import annotations

import re
import subprocess


def get_repo_info() -> tuple[str, str]:
    """Extract the GitHub owner and repository name from ``origin``."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not determine GitHub repo from git remote origin: {exc}") from exc

    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", result.stdout.strip())
    if match:
        return match.group(1), match.group(2)
    raise ValueError("Could not determine GitHub repo from git remote origin")
