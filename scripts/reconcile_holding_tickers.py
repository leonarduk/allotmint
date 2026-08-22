"""Resolve incorrectly suffixed holdings using persisted/Yahoo metadata."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from backend.common.instruments import resolve_instrument_ticker
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


def reconcile_account_file(path: Path, *, write: bool = False) -> dict[str, list[str]]:
    """Resolve ``.L`` holdings in one account file and optionally save changes."""
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    changed: list[str] = []
    unresolved: list[str] = []

    holdings = document.get("holdings", [])
    if not isinstance(holdings, list):
        # A malformed account file (e.g. ``holdings`` persisted as a dict)
        # would otherwise silently iterate over dict keys as if they were
        # holdings and risk writing corrupted data. This is a batch script —
        # one bad file should be skipped with a warning, not abort the run
        # or raise mid-write.
        logger.warning(
            "Skipping %s: 'holdings' is %s, expected a list",
            sanitise_log_value(str(path)),
            type(holdings).__name__,
        )
        return {"changed": changed, "unresolved": unresolved}

    for holding in holdings:
        ticker = str(holding.get("ticker", "")).strip().upper()
        if not ticker.endswith(".L"):
            continue
        symbol = ticker.removesuffix(".L")
        # Only try (and persist) live Yahoo lookups when actually writing;
        # a dry run must not mutate instrument metadata as a side effect.
        resolved = resolve_instrument_ticker(symbol, create_missing=write)
        if resolved is None:
            unresolved.append(ticker)
        elif resolved != ticker:
            holding["ticker"] = resolved
            changed.append(f"{ticker} -> {resolved}")

    if write and changed:
        backup_path = path.with_suffix(path.suffix + ".bak")
        if not backup_path.exists():
            # Preserve the earliest known-good copy: a second run must not let
            # a fresh backup overwrite the original pre-reconciliation state.
            _atomic_write_text(backup_path, path.read_text(encoding="utf-8"))
        _atomic_write_text(path, json.dumps(document, indent=2) + "\n")
    return {"changed": changed, "unresolved": unresolved}


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file + rename so a failed write
    (e.g. disk full) cannot leave ``path`` partially overwritten. The temp
    file is fsync'd before the rename so the new content survives a crash
    immediately after this call returns."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve account holdings against instrument metadata (dry-run by default)."
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Account JSON files (defaults to every account file)")
    parser.add_argument("--write", action="store_true", help="Write resolved tickers back to account files")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Required alongside --write with no explicit paths, to confirm "
        "writing every account file under the accounts root is intentional",
    )
    args = parser.parse_args()
    paths = args.paths or sorted(config.accounts_root.glob("*/*.json"))

    if args.write and not args.paths and not args.all:
        parser.error("--write with no explicit paths also requires --all (writes every account file)")

    for path in paths:
        result = reconcile_account_file(path, write=args.write)
        if result["changed"] or result["unresolved"]:
            print(f"{path}:")
            for change in result["changed"]:
                print(f"  resolved: {change}")
            for ticker in result["unresolved"]:
                print(f"  needs manual mapping: {ticker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
