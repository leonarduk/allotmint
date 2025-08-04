# ────────────────────────────────────────────────────────────────────
# backend/common/portfolio_loader.py
# Lightweight portfolio loader with optional "lazy" mode
# ────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml  # PyYAML

from backend.common.group_portfolio import list_groups

# Where your portfolio YAML/JSON lives
_PORTFOLIO_PATH = Path("data/portfolios")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _portfolio_files() -> List[Path]:
    """
    Return every *.yml, *.yaml, and *.json file in the portfolio folder.

    Uses lists (not generators) so we can concatenate safely.
    """
    if not _PORTFOLIO_PATH.exists():
        return []

    yml  = list(_PORTFOLIO_PATH.glob("*.yml"))
    yaml_files = list(_PORTFOLIO_PATH.glob("*.yaml"))
    json_files = list(_PORTFOLIO_PATH.glob("*.json"))
    return sorted(yml + yaml_files + json_files)


def _load_file(path: Path) -> Dict[str, Any]:
    """Load a single YAML or JSON portfolio file into a dict."""
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(fh) or {}
        return json.load(fh)


def _raw_portfolios() -> List[Dict[str, Any]]:
    """Return list of raw dicts – **no** valuation side-effects."""
    return [_load_file(p) for p in _portfolio_files()]


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────
def list_portfolios(*, lazy: bool = False):
    """
    Parameters
    ----------
    lazy : bool, default False
        • True  → just parse the files and return plain dicts
        • False → import backend.common.portfolio (heavy) which
                   attaches valuations and snapshots
    """
    if lazy:
        return _raw_portfolios()

    # Heavy path: keeps original behaviour for code that still needs it
    return list_groups()
