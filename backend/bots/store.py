"""Where bot run records and settings live.

``BOTS_STORAGE_URI`` is a base location (``file://`` directory or ``s3://``
prefix); documents are stored under it as ``runs/<bot_id>.json`` and
``settings.json`` via :func:`backend.common.storage.get_storage`. Resolved on
every call (not at import) so tests and Lambdas that set the env var late are
honoured, mirroring ``backend.common.pension_snapshots`` (#5010).
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.common.storage import JSONStorage, get_storage
from backend.config import config

BOTS_STORAGE_ENV = "BOTS_STORAGE_URI"


def _default_base() -> str:
    root = Path(config.repo_root or Path(__file__).resolve().parents[2])
    return f"file://{root / 'data' / 'bots'}"


def storage_base() -> str:
    return (os.getenv(BOTS_STORAGE_ENV) or _default_base()).rstrip("/\\")


def storage_for(key: str) -> JSONStorage:
    """Return the JSON document ``key`` (e.g. ``runs/price-refresh.json``)."""

    return get_storage(f"{storage_base()}/{key}", param_type="String")
