"""Resolve incorrectly suffixed holdings using persisted/Yahoo metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from backend.common.instruments import resolve_instrument_ticker
from backend.config import config


def reconcile_account_file(path: Path, *, write: bool = False) -> dict[str, list[str]]:
    """Resolve ``.L`` holdings in one account file and optionally save changes."""
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    changed: list[str] = []
    unresolved: list[str] = []

    for holding in document.get("holdings", []):
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
    (e.g. disk full) cannot leave ``path`` partially overwritten."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve account holdings against instrument metadata (dry-run by default)."
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, help="Account JSON files (defaults to every account file)"
    )
    parser.add_argument(
        "--write", action="store_true", help="Write resolved tickers back to account files"
    )
    args = parser.parse_args()
    paths = args.paths or sorted(config.accounts_root.glob("*/*.json"))

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
