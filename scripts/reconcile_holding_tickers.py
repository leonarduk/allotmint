"""Resolve incorrectly suffixed holdings using persisted/Yahoo metadata."""

from __future__ import annotations

import argparse
import json
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
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return {"changed": changed, "unresolved": unresolved}


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
