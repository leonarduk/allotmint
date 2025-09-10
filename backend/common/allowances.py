from __future__ import annotations

"""Allowance tracking utilities.

This module provides helpers to load yearly contribution data from a simple
JSON structure and compute remaining allowances for different account types.
The contributions are expected under ``data/allowances/<owner>.json`` with the
following structure::

    {
        "2024-2025": {"ISA": 5000, "pension": 10000},
        "2025-2026": {"ISA": 0, "pension": 0}
    }

Only the parts required for the tests are implemented; the functions are
resilient to missing data and return zero contributions by default.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Dict, Optional

from backend.config import config

# Default annual limits (GBP) for supported account types
ALLOWANCE_LIMITS: Dict[str, float] = {
    "ISA": 20_000.0,
    "pension": 40_000.0,
}


def _data_root(root: Optional[Path | str] = None) -> Path:
    base = (
        Path(root)
        if root is not None
        else Path(config.data_root) if config.data_root else Path(__file__).resolve().parents[2] / "data"
    )
    return base / "allowances"


def current_tax_year(today: Optional[dt.date] = None) -> str:
    """Return the UK tax year string for ``today``.

    The UK tax year runs from 6 April to 5 April the following year. The result
    is formatted as ``"YYYY-YYYY"`` representing the start and end years.
    """

    today = today or dt.date.today()
    start_year = today.year if (today.month, today.day) >= (4, 6) else today.year - 1
    return f"{start_year}-{start_year + 1}"


def load_yearly_contributions(
    owner: str,
    tax_year: str,
    root: Optional[Path | str] = None,
) -> Dict[str, float]:
    """Load contribution totals for ``owner`` and ``tax_year``.

    Missing files or malformed data result in an empty mapping.
    """

    path = _data_root(root) / f"{owner}.json"
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    year_data = raw.get(tax_year, {})
    results: Dict[str, float] = {}
    for key, value in year_data.items():
        try:
            results[key] = float(value)
        except (TypeError, ValueError):
            continue
    return results


def remaining_allowances(
    owner: str,
    tax_year: str,
    limits: Optional[Dict[str, float]] = None,
    root: Optional[Path | str] = None,
) -> Dict[str, Dict[str, float]]:
    """Return allowance usage and remaining amounts for ``owner``.

    ``limits`` may override the default :data:`ALLOWANCE_LIMITS`.
    """

    limits = limits or ALLOWANCE_LIMITS
    contribs = load_yearly_contributions(owner, tax_year, root)
    results: Dict[str, Dict[str, float]] = {}
    for acct, limit in limits.items():
        used = float(contribs.get(acct, 0.0))
        remaining = max(0.0, float(limit) - used)
        results[acct] = {
            "used": round(used, 2),
            "limit": float(limit),
            "remaining": round(remaining, 2),
        }
    return results


__all__ = [
    "ALLOWANCE_LIMITS",
    "current_tax_year",
    "load_yearly_contributions",
    "remaining_allowances",
]
