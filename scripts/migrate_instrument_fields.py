#!/usr/bin/env python3
"""Backfill new instrument fields.

This migration scans ``data/instruments`` and ensures ``asset_class``,
``industry`` and ``region`` keys exist on every JSON file.  Missing
fields are initialised to ``null`` so subsequent runs or manual edits
can fill in real values.

Run with::

    python scripts/migrate_instrument_fields.py

The script is idempotent – running it multiple times is safe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("DATA_ROOT", ROOT / "data"))
INSTRUMENTS_DIR = DATA_ROOT / "instruments"
NEW_FIELDS = {
    "asset_class": None,
    "industry": None,
    "region": None,
}


def update_file(path: Path) -> bool:
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - best effort logging
        print(f"Skipping {path}: {exc}")
        return False
    changed = False
    for field, default in NEW_FIELDS.items():
        if field not in data:
            data[field] = default
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    updated = 0
    for file in INSTRUMENTS_DIR.rglob("*.json"):
        if update_file(file):
            updated += 1
            print(f"Updated {file}")
    print(f"Migration complete; {updated} file(s) modified.")


if __name__ == "__main__":
    main()
