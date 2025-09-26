"""Shared helpers for resolving account directories."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from backend.common import data_loader
from backend.config import config


def resolve_accounts_root(request: Request) -> Path:
    """Determine the accounts root directory for the current request.

    Preference is given to ``request.app.state.accounts_root`` when it points to
    an existing directory. When missing or invalid the function falls back to
    the configured repository paths, ultimately defaulting to the standard data
    directory discovered via :func:`data_loader.resolve_paths`.
    """

    accounts_root_value = getattr(request.app.state, "accounts_root", None)
    if accounts_root_value:
        candidate = Path(accounts_root_value).expanduser()
        resolved_candidate = candidate.resolve(strict=False)
        request.app.state.accounts_root = resolved_candidate
        return resolved_candidate

    paths = data_loader.resolve_paths(config.repo_root, config.accounts_root)
    root = paths.accounts_root
    if not root.exists():
        fallback_paths = data_loader.resolve_paths(None, None)
        root = fallback_paths.accounts_root

    resolved_root = Path(root).expanduser().resolve()
    request.app.state.accounts_root = resolved_root
    return resolved_root
