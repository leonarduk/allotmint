"""Backfill ``asset_class`` and exposure-based fund sectors in instrument metadata.

Applies :func:`backend.common.instrument_classification.classify_instrument`
(plus the manual overrides file) to every ``instruments/<EXCHANGE>/<SYMBOL>.json``
under the data root. Dry-run by default; ``--write`` saves changed files,
keeping each file's key order so the diff shows only the changed fields.
See issue #9196 and docs/instrument-classification.md.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.common.instrument_classification import (
    classify_instrument,
    load_classification_overrides,
    overrides_path,
)

logger = logging.getLogger(__name__)


def _ticker_for(path: Path, meta: dict[str, Any]) -> str:
    raw = meta.get("ticker")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    if path.parent.name == "Cash":
        return f"CASH.{path.stem.upper()}"
    return f"{path.stem.upper()}.{path.parent.name.upper()}"


def classify_file(
    path: Path,
    overrides: dict[str, dict[str, Any]],
    *,
    write: bool = False,
) -> Optional[dict[str, tuple[Any, Any]]]:
    """Classify one metadata file; return ``{field: (before, after)}`` changes.

    Returns ``None`` for an unreadable file (logged and skipped) so one bad
    file cannot abort a backfill.
    """
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Skipping unreadable %s: %s", path, exc)
        return None
    if not isinstance(meta, dict):
        logger.warning("Skipping %s: not a JSON object", path)
        return None

    ticker = _ticker_for(path, meta)
    updates = classify_instrument({**meta, "ticker": ticker}, overrides.get(ticker))
    changes = {field: (meta.get(field), value) for field, value in updates.items() if meta.get(field) != value}
    if write and changes:
        meta.update(updates)
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changes


def classify_all(
    instruments_dir: Path,
    overrides: dict[str, dict[str, Any]],
    *,
    write: bool = False,
) -> dict[str, dict[str, tuple[Any, Any]]]:
    """Classify every instrument file; return the changes keyed by file."""
    report: dict[str, dict[str, tuple[Any, Any]]] = {}
    # One level of exchange folders only: ``groupings/`` and other nested
    # catalogues are not instrument records.
    for path in sorted(instruments_dir.glob("*/*.json")):
        if path.parent.name == "groupings":
            continue
        changes = classify_file(path, overrides, write=write)
        if changes:
            report[path.relative_to(instruments_dir).as_posix()] = changes
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] + " (dry-run by default).")
    parser.add_argument(
        "--instruments-dir",
        type=Path,
        default=None,
        help="Instrument metadata directory (default: <data_root>/instruments)",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help="Manual overrides JSON (default: <data_root>/instrument_classification_overrides.json)",
    )
    parser.add_argument("--write", action="store_true", help="Save changes (default: report only)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # overrides_path() resolves the data root, falling back to the bundled
    # data/ directory when none is configured.
    instruments_dir = args.instruments_dir or overrides_path().parent / "instruments"
    if not instruments_dir.is_dir():
        parser.error(f"instruments directory not found: {instruments_dir}")
    overrides = load_classification_overrides(args.overrides or overrides_path())

    report = classify_all(instruments_dir, overrides, write=args.write)
    for rel_path, changes in report.items():
        detail = "; ".join(f"{field}: {before!r} -> {after!r}" for field, (before, after) in changes.items())
        print(f"{rel_path}: {detail}")
    verb = "Updated" if args.write else "Would update"
    print(f"{verb} {len(report)} file(s) in {instruments_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
