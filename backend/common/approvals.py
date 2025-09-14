from __future__ import annotations

"""Helpers for loading and validating trade approvals."""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from backend.config import config

logger = logging.getLogger(__name__)


def approvals_path(owner: str, accounts_root: Path | None = None) -> Path:
    """Return the path to ``owner``'s approvals file.

    ``FileNotFoundError`` is raised when the owner's accounts directory does not
    exist.  Callers are expected to handle or propagate this exception.
    """

    root = Path(accounts_root or config.accounts_root)
    owner_dir = root / owner
    if not owner_dir.exists():
        raise FileNotFoundError(owner_dir)
    return owner_dir / "approvals.json"


def load_approvals(owner: str, accounts_root: Optional[Path] = None) -> Dict[str, date]:
    """Return mapping of ticker -> approval date for ``owner``.

    Expects ``approvals.json`` in the owner's accounts directory containing either
    a list of objects ``{"ticker": ..., "approved_on": ...}`` or a dict with key
    ``"approvals"`` containing that list.  Ticker symbols are normalised to
    uppercase.
    """

    path = approvals_path(owner, accounts_root)
    if not path.exists():
        logger.info("approvals file for '%s' not found at %s", owner, path)
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to read approvals for %s: %s", owner, exc)
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
        except (TypeError, ValueError):
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


def save_approvals(
    owner: str, approvals: Dict[str, date], accounts_root: Path | None = None
) -> None:
    """Persist ``approvals`` for ``owner`` to ``approvals.json``."""

    path = approvals_path(owner, accounts_root)
    entries = [
        {"ticker": t.upper(), "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    try:
        path.write_text(json.dumps({"approvals": entries}, indent=2, sort_keys=True))
    except OSError as exc:
        logger.error("failed to write approvals for %s to %s: %s", owner, path, exc)
        raise


def upsert_approval(
    owner: str,
    ticker: str,
    approved_on: date,
    accounts_root: Path | None = None,
) -> Dict[str, date]:
    """Add or update a single ticker approval and return the updated mapping."""

    approvals = load_approvals(owner, accounts_root)
    approvals[ticker.upper()] = approved_on
    try:
        save_approvals(owner, approvals, accounts_root)
    except OSError:
        logger.error("failed to persist approval for %s/%s", owner, ticker)
        raise
    return approvals


def delete_approval(
    owner: str, ticker: str, accounts_root: Path | None = None
) -> Dict[str, date]:
    """Remove ``ticker`` from approvals and return the updated mapping."""

    approvals = load_approvals(owner, accounts_root)
    approvals.pop(ticker.upper(), None)
    try:
        save_approvals(owner, approvals, accounts_root)
    except OSError:
        logger.error("failed to persist approval removal for %s/%s", owner, ticker)
        raise
    return approvals

