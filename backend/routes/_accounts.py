"""Shared helpers for resolving account directories."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Request

from backend.common import data_loader
from backend.config import config


def resolve_accounts_root(request: Request) -> Path:
    """Determine the accounts root directory for the current request.

    Preference is given to ``request.app.state.accounts_root`` when available,
    even if the directory has not been created yet. When the state is missing
    or cannot be resolved to a valid path the function falls back to the
    configured repository paths, ultimately defaulting to the standard data
    directory discovered via :func:`data_loader.resolve_paths`.
    """

    accounts_root_value = getattr(request.app.state, "accounts_root", None)
    if accounts_root_value is not None:
        try:
            cached_path = Path(accounts_root_value).expanduser()
            resolved_cached = cached_path.resolve(strict=False)
        except (TypeError, ValueError, OSError):
            cached_path = None
            resolved_cached = None
        else:
            request.app.state.accounts_root = resolved_cached
            if hasattr(request.app.state, "accounts_root_is_global"):
                # Preserve a previously cached "global" flag so callers can
                # detect that the application is still operating against the
                # fallback data directory. This is important for routes such
                # as the transactions endpoints which require an explicitly
                # configured accounts directory. Only clear the flag when it
                # is not already marked as global.
                if getattr(request.app.state, "accounts_root_is_global", None) is not True:
                    request.app.state.accounts_root_is_global = False
            return resolved_cached

        request.app.state.accounts_root = None
        if hasattr(request.app.state, "accounts_root_is_global"):
            request.app.state.accounts_root_is_global = False

    paths = data_loader.resolve_paths(config.repo_root, config.accounts_root)
    primary_root = paths.accounts_root
    if primary_root.exists():
        resolved_primary = primary_root.expanduser().resolve()
        request.app.state.accounts_root = resolved_primary
        request.app.state.accounts_root_is_global = False
        return resolved_primary

    fallback_paths = data_loader.resolve_paths(None, None)
    fallback_root = fallback_paths.accounts_root
    resolved_fallback = fallback_root.expanduser().resolve()
    request.app.state.accounts_root = resolved_fallback
    request.app.state.accounts_root_is_global = True
    return resolved_fallback


def resolve_owner_directory(accounts_root: Optional[Path], owner: str) -> Optional[Path]:
    """Return the directory for ``owner`` if it exists under ``accounts_root``.

    The lookup is case-insensitive: the first matching directory name is
    returned even if the provided ``owner`` casing differs from the on-disk
    representation.
    """

    if not accounts_root or not owner:
        return None

    root = Path(accounts_root)
    if not root.exists():
        return None

    direct = root / owner
    if direct.exists():
        return direct

    owner_casefold = owner.casefold()
    try:
        for candidate in root.iterdir():
            if candidate.is_dir() and candidate.name.casefold() == owner_casefold:
                return candidate
    except OSError:
        return None

    return None
