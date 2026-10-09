"""JSON state for the fund upkeep bot: proposals, owner settings, last-run snapshots (#10482).

Files live under ``<data_root>/fund_upkeep/`` (next to the audit directory).
Writes go to a temporary file and are renamed into place, so a crash never
leaves half a file. Tests monkeypatch :func:`store_dir`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

LOCK = threading.RLock()


def store_dir() -> Path:
    data_root = getattr(config, "data_root", None)
    base = Path(data_root) if data_root else Path(__file__).resolve().parents[2] / "data"
    return base / "fund_upkeep"


def read_json(name: str, default: Any) -> Any:
    """The parsed ``name`` file, or ``default`` when it is missing or unreadable."""
    path = store_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable fund upkeep file %s: %s", sanitise_log_value(path), sanitise_log_value(exc))
        return default


def write_json(name: str, data: Any) -> None:
    path = store_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
