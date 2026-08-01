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
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not determine GitHub repo from git remote origin: {exc}") from exc

    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", result.stdout.strip())
    if match:
        return match.group(1), match.group(2)
    raise ValueError("Could not determine GitHub repo from git remote origin")


def get_repo_root() -> str:
    """Return the absolute path to the current git repository's root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not determine repo root from git: {exc}") from exc
    return result.stdout.strip()
