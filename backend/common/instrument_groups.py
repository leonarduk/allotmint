"""Helpers for persisting the list of instrument grouping labels."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List

from backend.config import config

logger = logging.getLogger(__name__)


def _data_root() -> Path:
    """Return the configured data root or fall back to the repo ``data`` dir."""

    root = config.data_root
    if root is not None:
        return root
    return Path(__file__).resolve().parents[2] / "data"


def _groups_path() -> Path:
    return _data_root() / "instrument-groups.json"


def _normalise(values: Iterable[str]) -> List[str]:
    seen: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        key = trimmed.casefold()
        if key not in seen:
            seen[key] = trimmed
    return sorted(seen.values(), key=str.casefold)


def load_groups() -> List[str]:
    """Return the persisted grouping labels, falling back to an empty list."""

    path = _groups_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        logger.warning("Invalid instrument groups JSON %s: %s", path, exc)
        return []
    except Exception:  # pragma: no cover - unexpected IO errors
        logger.exception("Failed to load instrument groups from %s", path)
        raise

    if isinstance(data, dict):
        data = data.get("groups", [])
    if not isinstance(data, list):
        return []

    return _normalise(item for item in data if isinstance(item, str))


def save_groups(groups: Iterable[str]) -> Path:
    """Persist the provided grouping labels returning the written path."""

    values = _normalise(groups)
    path = _groups_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(values, fh, indent=2)
        fh.write("\n")
    return path


def add_group(name: str) -> List[str]:
    """Ensure *name* is present in the catalogue and return the full list."""

    if not isinstance(name, str):
        raise TypeError("group name must be a string")
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("group name must be non-empty")

    groups = load_groups()
    lower = {g.casefold(): g for g in groups}
    if trimmed.casefold() not in lower:
        groups.append(trimmed)
        save_groups(groups)
        groups = load_groups()
    return groups

