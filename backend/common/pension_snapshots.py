from __future__ import annotations

"""Persisted pot-value snapshots for pension YTD/period-over-period tracking.

Mirrors ``backend.common.goals``'s use of ``backend.common.storage.get_storage``
for env-var-configurable JSON persistence (local file, S3 or SSM Parameter
Store, selected via URI scheme).
"""

import datetime as dt
import os
from pathlib import Path
from typing import Any, Dict, Optional

from backend.common.storage import JSONStorage, get_storage
from backend.config import config

_DEFAULT_SNAPSHOTS_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'pension_snapshots.json'}"
)


def _get_storage() -> JSONStorage:
    """Resolve the snapshots storage backend, reading ``PENSION_SNAPSHOTS_URI``
    at call time rather than import time.

    A module-level constant would freeze whichever value (or fallback) was in
    effect the moment this module was first imported — e.g. before a
    framework or test finishes setting env vars — and never re-evaluate it.
    Resolving lazily on each call means the configured backend is always
    honoured once the env var is actually set. Intentionally not cached at
    module level (#5010).
    """
    try:
        return get_storage(os.getenv("PENSION_SNAPSHOTS_URI", _DEFAULT_SNAPSHOTS_URI))
    except Exception:
        return get_storage(_DEFAULT_SNAPSHOTS_URI)


def _load_raw() -> Dict[str, Dict[str, Any]]:
    data = _get_storage().load()
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def get_previous_snapshot(owner: str) -> Optional[Dict[str, Any]]:
    """Return the last persisted pot snapshot for ``owner``, or ``None``."""
    return _load_raw().get(owner)


def ytd_baseline_pot_gbp(previous: Optional[Dict[str, Any]], current_pot_gbp: float, today: dt.date) -> float:
    """Return the pot value to use as the start-of-year YTD baseline.

    Falls back to the last known pot value on year rollover (or the current
    pot if no snapshot has ever been recorded), since only one snapshot per
    report run is kept rather than a full intra-year history.
    """
    if not previous:
        return current_pot_gbp
    if previous.get("year") == today.year:
        return float(previous.get("start_of_year_pot_gbp", current_pot_gbp))
    return float(previous.get("last_pot_gbp", current_pot_gbp))


def previous_period_pot_gbp(previous: Optional[Dict[str, Any]], current_pot_gbp: float) -> float:
    """Return the pot value recorded at the previous report run, or the current pot."""
    if not previous:
        return current_pot_gbp
    return float(previous.get("last_pot_gbp", current_pot_gbp))


def record_snapshot(owner: str, *, pot_gbp: float, as_of: dt.date) -> None:
    """Persist ``pot_gbp`` as the latest known snapshot for ``owner``."""
    data = _load_raw()
    previous = data.get(owner)
    start_of_year_pot_gbp = ytd_baseline_pot_gbp(previous, pot_gbp, as_of)
    data[owner] = {
        "year": as_of.year,
        "start_of_year_pot_gbp": start_of_year_pot_gbp,
        "last_pot_gbp": pot_gbp,
        "last_as_of": as_of.isoformat(),
    }
    _get_storage().save(data)


__all__ = [
    "get_previous_snapshot",
    "ytd_baseline_pot_gbp",
    "previous_period_pot_gbp",
    "record_snapshot",
]
