"""Where trend-watch keeps its reports, detector state and mute lists (#10476).

Per owner, under one prefix:

* ``trend_watch/<owner>/<date>.json`` -- each run's report;
* ``trend_watch/<owner>/latest.json`` -- a copy of the newest report, so serving
  it needs no listing;
* ``trend_watch/<owner>/state.json`` -- every ticker's signals at the last run,
  so the next run can tell new signals from old ones;
* ``trend_watch/<owner>/mutes.json`` -- holdings the owner has said are
  deliberate long-term or residual positions.

The prefix is ``TREND_WATCH_URI`` when set, else ``s3://$DATA_BUCKET/trend_watch``
on AWS, else ``data/trend_watch`` in the repo, through the same JSON storage
abstraction as the other per-user documents (``backend.common.storage``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.storage import JSONStorage, get_storage
from backend.config import config

_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InvalidOwner(ValueError):
    """The owner id cannot be used as a storage key."""


def _base_uri() -> str:
    explicit = os.getenv("TREND_WATCH_URI")
    if explicit:
        return explicit.rstrip("/")
    bucket = os.getenv("DATA_BUCKET")
    if bucket:
        return f"s3://{bucket}/trend_watch"
    root = config.repo_root or Path(__file__).resolve().parents[2]
    return f"file://{Path(root) / 'data' / 'trend_watch'}"


def clean_owner(owner: str) -> str:
    cleaned = (owner or "").strip()
    if not _OWNER_RE.match(cleaned) or ".." in cleaned:
        raise InvalidOwner(f"invalid owner {owner!r}")
    return cleaned


def _doc(owner: str, name: str) -> JSONStorage:
    return get_storage(f"{_base_uri()}/{clean_owner(owner)}/{name}.json")


def save_report(owner: str, report: Dict[str, Any]) -> None:
    run_date = str(report.get("run_date") or "")
    if not _DATE_RE.match(run_date):
        raise ValueError(f"report run_date must be YYYY-MM-DD, got {run_date!r}")
    _doc(owner, run_date).save(report)
    _doc(owner, "latest").save(report)


def load_latest(owner: str) -> Optional[Dict[str, Any]]:
    report = _doc(owner, "latest").load()
    return report or None


def load_state(owner: str) -> Dict[str, Dict[str, Any]]:
    state = _doc(owner, "state").load()
    tickers = state.get("tickers") if isinstance(state, dict) else None
    return tickers if isinstance(tickers, dict) else {}


def save_state(owner: str, tickers: Dict[str, Dict[str, Any]]) -> None:
    _doc(owner, "state").save({"tickers": tickers})


def load_mutes(owner: str) -> List[str]:
    data = _doc(owner, "mutes").load()
    tickers = data.get("tickers") if isinstance(data, dict) else None
    return sorted({str(t).upper() for t in tickers or [] if str(t).strip()})


def set_muted(owner: str, ticker: str, muted: bool) -> List[str]:
    """Mute or unmute ``ticker`` for ``owner``; return the new mute list."""

    ticker = (ticker or "").strip().upper()
    if not ticker or len(ticker) > 32:
        raise ValueError("ticker is required")
    current = set(load_mutes(owner))
    if muted:
        current.add(ticker)
    else:
        current.discard(ticker)
    tickers = sorted(current)
    _doc(owner, "mutes").save({"tickers": tickers})
    return tickers
