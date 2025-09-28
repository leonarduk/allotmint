"""Shared helpers for resolving account directories."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Request

from backend.common import data_loader
from backend.config import config


def resolve_accounts_root(request: Request, *, allow_missing: bool = False) -> Path:
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
            cached_path = Path(os.fspath(accounts_root_value)).expanduser()
        except (TypeError, ValueError, OSError):
            cached_path = None
            resolved_cached = None
        else:
            try:
                resolved_cached = cached_path.resolve(strict=False)
            except OSError:
                resolved_cached = None
            if cached_path.exists():
                if not cached_path.is_dir():
                    cached_path = None
                    resolved_cached = None
                else:
                    resolved_cached = cached_path.expanduser().resolve()
            elif allow_missing:
                resolved_cached = resolved_cached or cached_path
            else:
                cached_path = None
                resolved_cached = None

        if resolved_cached is not None:
            request.app.state.accounts_root = resolved_cached
            if hasattr(request.app.state, "accounts_root_is_global"):
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
