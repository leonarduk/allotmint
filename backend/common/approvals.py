from __future__ import annotations

"""Helpers for loading and validating trade approvals."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from backend.config import config
from backend.common.data_loader import resolve_paths


def load_approvals(owner: str, accounts_root: Optional[Path] = None) -> Dict[str, date]:
    """Return mapping of ticker -> approval date for ``owner``.

    Expects ``approvals.json`` in the owner's accounts directory containing either
    a list of objects ``{"ticker": ..., "approved_on": ...}`` or a dict with key
    ``"approvals"`` containing that list.  Ticker symbols are normalised to
    uppercase.
    """
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    path = root / owner / "approvals.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    entries = data.get("approvals") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return {}
    out: Dict[str, date] = {}
    for row in entries:
        ticker = (row.get("ticker") or "").upper()
        when = row.get("approved_on") or row.get("date")
        try:
            out[ticker] = datetime.fromisoformat(str(when)).date()
        except Exception:
            continue
    return out


def add_trading_days(start: date, n: int) -> date:
    """Return ``start`` advanced by ``n`` trading days (skipping weekends)."""
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def is_approval_valid(approved_on: date | None, as_of: date, days: int | None = None) -> bool:
    """Return ``True`` if approval granted on ``approved_on`` is still valid at ``as_of``."""
    if approved_on is None:
        return False
    valid = days or config.approval_valid_days or 0
    expiry = add_trading_days(approved_on, max(0, valid - 1))
    return as_of <= expiry
