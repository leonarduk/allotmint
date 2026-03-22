"""Filesystem bootstrap helpers for account-root resolution and test isolation."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.common.data_loader import ResolvedPaths, resolve_paths
from backend.common.transaction_reconciliation import reconcile_transactions_with_holdings
from backend.config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimePaths:
    paths: ResolvedPaths
    accounts_root: Path
    accounts_root_is_global: bool
    temp_dirs: list[Path]


def configure_runtime_paths(cfg: Config) -> RuntimePaths:
    """Resolve runtime paths, isolate test data when needed, and reconcile holdings."""

    configured_root = getattr(cfg, "accounts_root", None)
    fallback_used = _configured_root_uses_global_fallback(configured_root)

    paths = resolve_paths(cfg.repo_root, cfg.accounts_root)
    accounts_root = paths.accounts_root
    original_accounts_root = accounts_root
    temp_dirs: list[Path] = []

    try:
        global_accounts_root = resolve_paths(None, None).accounts_root.resolve()
        fallback_used = fallback_used or accounts_root.resolve() == global_accounts_root
    except Exception:
        pass

    if os.getenv("TESTING"):
        isolated_root, temp_root = _isolate_accounts_root(paths=paths, accounts_root=accounts_root)
        if isolated_root is not None and temp_root is not None:
            temp_dirs.append(temp_root)
            accounts_root = isolated_root
            cfg.accounts_root = accounts_root
            tx_output = getattr(cfg, "transactions_output_root", None)
            if tx_output and Path(tx_output) == original_accounts_root:
                cfg.transactions_output_root = accounts_root

    try:
        reconcile_transactions_with_holdings(accounts_root)
    except Exception:
        logger.exception("Failed to reconcile holdings with transactions")

    return RuntimePaths(
        paths=paths,
        accounts_root=accounts_root,
        accounts_root_is_global=fallback_used,
        temp_dirs=temp_dirs,
    )


def _configured_root_uses_global_fallback(configured_root: object) -> bool:
    if not configured_root:
        return True
    try:
        return not Path(configured_root).expanduser().exists()
    except (TypeError, ValueError, OSError):
        return True


def _isolate_accounts_root(
    paths: ResolvedPaths, accounts_root: Path
) -> tuple[Path | None, Path | None]:
    try:
        accounts_root.relative_to(paths.repo_root)
    except ValueError:
        return None, None

    try:
        temp_root = Path(tempfile.mkdtemp(prefix="allotmint-accounts-"))
        isolated_root = temp_root / accounts_root.name
        shutil.copytree(accounts_root, isolated_root, dirs_exist_ok=True)
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning("Failed to isolate accounts root for tests: %s", exc)
        return None, None

    return isolated_root, temp_root
