# ────────────────────────────────────────────────────────────────────
# backend/common/portfolio_loader.py  ·  lightweight portfolio loader
# ────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml  # PyYAML

from backend.common.group_portfolio import list_groups

# ──────────────────────────────────────────────────────────────
# Where portfolio data lives (simplified)
#
#   ▸ data/accounts/<owner>/*.yml|yaml|json
#
# The legacy flat folder under ``data/portfolios`` has been removed
# to avoid accidental double‑loading.
# ──────────────────────────────────────────────────────────────
_DATA_ROOT: Path     = Path("data")
_ACCOUNTS_ROOT: Path = _DATA_ROOT / "accounts"

# module‑level logger
_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _portfolio_files() -> List[Path]:
    """Return every *.yml, *.yaml or *.json inside each owner’s folder."""
    paths: List[Path] = []

    _logger.debug("Scanning accounts root: %s", _ACCOUNTS_ROOT.resolve())

    if _ACCOUNTS_ROOT.exists():
        for owner_dir in _ACCOUNTS_ROOT.iterdir():
            if owner_dir.is_dir():
                _logger.debug("→ Scanning owner directory: %s", owner_dir)
                paths += list(owner_dir.glob("*.yml"))
                paths += list(owner_dir.glob("*.yaml"))
                paths += list(owner_dir.glob("*.json"))

    paths = sorted(paths)
    _logger.debug("Discovered %d portfolio file(s): %s", len(paths), paths)
    return paths


def _load_file(path: Path) -> Dict[str, Any]:
    """Parse a single YAML or JSON portfolio file into a dict."""
    _logger.debug("Loading portfolio file: %s", path)
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(fh) or {}
        return json.load(fh)


def _raw_portfolios() -> List[Dict[str, Any]]:
    """Return parsed dicts *as‑is* – **no** valuation side‑effects."""
    portfolios = [_load_file(p) for p in _portfolio_files()]
    _logger.debug("Loaded %d raw portfolio dict(s)", len(portfolios))
    return portfolios

@lru_cache(maxsize=1)
def _raw_portfolios_cached() -> list[dict[str, Any]]:
    """Same as _raw_portfolios() but memoised for the process lifetime."""
    return _raw_portfolios()

# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def list_portfolios(*, lazy: bool = False):
    """List every portfolio, optionally *lazily* with zero heavy look‑ups.

    Parameters
    ----------
    lazy : bool, default False
        ▸ **True**  – parse the files and return the plain dicts only.
        ▸ **False** – import `backend.common.group_portfolio` and let that
                       attach valuations / snapshots (original behaviour).
    """
    if lazy:
        return _raw_portfolios_cached()

    # Heavy path: keeps original behaviour for code that still needs it.
    return list_groups()


