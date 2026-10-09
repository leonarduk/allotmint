"""Where data steward run reports are kept (#10471).

Each run is saved as ``<YYYY-MM-DD>.json`` (a later run the same day replaces it)
plus ``latest.json``, under ``DATA_STEWARD_REPORTS_URI`` when set (the nightly
Lambda points it at ``s3://<data bucket>/data_steward/reports``), otherwise
``{data_root}/data_steward/reports``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from backend.common.storage import FileJSONStorage, JSONStorage, S3JSONStorage
from backend.config import config

LATEST_NAME = "latest.json"


def reports_location() -> str:
    configured = os.getenv("DATA_STEWARD_REPORTS_URI", "").strip()
    if configured:
        return configured.rstrip("/")
    data_root = getattr(config, "data_root", None)
    base = Path(data_root) if data_root else Path(__file__).resolve().parents[2] / "data"
    return str(base / "data_steward" / "reports")


def _storage(name: str) -> JSONStorage:
    location = reports_location()
    if location.startswith("s3://"):
        parsed = urlparse(location)
        prefix = parsed.path.strip("/")
        return S3JSONStorage(bucket=parsed.netloc, key=f"{prefix}/{name}" if prefix else name)
    return FileJSONStorage(Path(location) / name)


def save_report(report: Dict[str, Any]) -> None:
    day = str(report.get("started_at") or "")[:10] or "undated"
    _storage(f"{day}.json").save(report)
    _storage(LATEST_NAME).save(report)


def load_latest_report() -> Optional[Dict[str, Any]]:
    report = _storage(LATEST_NAME).load()
    return report or None
