"""Explicitly resolve mistickered holdings and rewrite account documents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.common.instruments import is_sedol, resolve_instrument_ticker  # noqa: E402


def reconcile_file(path: Path) -> dict[str, list[str]]:
    """Resolve unresolved ``.L`` holdings in one account document."""

    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    changed: list[str] = []
    manual: list[str] = []
    for holding in payload.get("holdings", []):
        ticker = str(holding.get("ticker", "")).strip().upper()
        symbol, separator, exchange = ticker.partition(".")
        if is_sedol(symbol):
            manual.append(symbol)
            if separator:
                holding["ticker"] = symbol
                changed.append(f"{ticker} -> {symbol}")
            continue
        if exchange != "L":
            continue
        resolved = resolve_instrument_ticker(symbol)
        if resolved and resolved != ticker:
            holding["ticker"] = resolved
            changed.append(f"{ticker} -> {resolved}")
    if changed:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"changed": changed, "manual_mapping_required": manual}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "accounts_root", type=Path, help="Directory containing owner/account JSON files"
    )
    args = parser.parse_args()
    report = {
        str(path): result
        for path in sorted(args.accounts_root.glob("*/*.json"))
        if any((result := reconcile_file(path)).values())
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
