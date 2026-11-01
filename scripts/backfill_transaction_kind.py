"""Backfill the structured cash ``kind`` on stored transactions (#10797).

Walks ``<accounts root>/<owner>/*_transactions.json`` and, for every row whose
``kind`` is missing or null, sets the kind
:func:`backend.common.cash_kind.classify_cash_kind` gives it. A row that
already has a ``kind`` is never changed, so running the script again changes
nothing. Cash rows (``DEPOSIT``, ``TRANSFER_IN``, ``WITHDRAWAL``,
``INTEREST``, ``FEES``) the rules leave unclassified are listed so they can be
set by hand; their ``kind`` stays null and readers keep using comment rules.

Rows with the legacy ``kind="account"`` (written by the Moneyhub API importer,
``backend/importers/moneyhub_api.py``) are deliberately left alone as well:
``"account"`` marks an account-level cash row, not a cash classification, and
those rows carry Moneyhub's own category as their ``type``, not one of the
types the rules are written for. They are counted per file and in total so the
rows still without a real cash kind stay visible (#11192).

The account a row belongs to is the file's ``account_type`` (as written by the
transactions API), else its ``account``, else the file name before
``_transactions.json``.

A file with classified rows is rewritten whole with ``json.dumps`` (2-space
indent, key order as loaded, whether it ended with a newline kept). A file
already in that layout shows only the new ``kind`` values in a diff; a
hand-edited file with other indentation or spacing is reformatted throughout.
``--dry-run`` reports what would change without writing anything, including
a separate list of files whose layout differs from that ``json.dumps`` output:
"would be rewritten and reformatted" when the file has rows to classify, or
"would be reformatted if written" when it has none (and so is left alone).
Files with nothing to classify are not touched.

Usage::

    python -m scripts.backfill_transaction_kind /path/to/allotmint-data/accounts [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.common.cash_kind import CASH_TYPES, classify_cash_kind

_SUFFIX = "_transactions.json"
# Legacy kind the Moneyhub API importer writes; kept as is (see the module docstring).
_LEGACY_ACCOUNT_KIND = "account"


def _account_name(path: Path, data: Dict[str, Any]) -> str:
    """The first non-blank string of ``account_type`` then ``account``, else the file name.

    Empty, whitespace-only and non-string values count as absent.
    """
    for key in ("account_type", "account"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return path.name[: -len(_SUFFIX)]


def _is_cash_row(tx: Dict[str, Any]) -> bool:
    tx_type = str(tx.get("type") or "").strip().upper()
    return tx_type in CASH_TYPES and not (tx_type == "TRANSFER_IN" and tx.get("ticker"))


def _classify_rows(rows: List[Dict[str, Any]], account: str) -> Tuple[Counter, List[Tuple[int, Dict[str, Any]]]]:
    """Set ``kind`` on unclassified rows in place; return kinds set and cash rows left unclassified."""
    added: Counter = Counter()
    unclassified: List[Tuple[int, Dict[str, Any]]] = []
    for index, tx in enumerate(rows):
        # Any set kind is kept, including the legacy "account" marker (#11192).
        if tx.get("kind"):
            continue
        kind = classify_cash_kind(tx, account)
        if kind:
            tx["kind"] = kind
            added[kind] += 1
        elif _is_cash_row(tx):
            unclassified.append((index, tx))
    return added, unclassified


def _legacy_account_rows(rows: List[Dict[str, Any]]) -> int:
    return sum(1 for tx in rows if tx.get("kind") == _LEGACY_ACCOUNT_KIND)


def _serialize(data: Any, raw: str) -> str:
    """The text a rewrite writes: 2-space indent, keeping whether ``raw`` ended with a newline."""
    return json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")


def _process(path: Path, dry_run: bool) -> Tuple[Counter, List[Tuple[int, Dict[str, Any]]], int, bool]:
    """Classify one file.

    Returns kinds set, cash rows left unclassified, legacy ``"account"`` rows
    kept, and whether its layout would change on a rewrite.
    """
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    transactions = data.get("transactions") if isinstance(data, dict) else None
    if not isinstance(transactions, list):
        return Counter(), [], 0, False
    # Compared before classification so only layout differences count, not new kinds.
    reformat = _serialize(data, raw) != raw
    rows = [tx for tx in transactions if isinstance(tx, dict)]
    legacy = _legacy_account_rows(rows)
    added, unclassified = _classify_rows(rows, _account_name(path, data))
    if added and not dry_run:
        path.write_text(_serialize(data, raw), encoding="utf-8")
    return added, unclassified, legacy, reformat


def _describe(index: int, tx: Dict[str, Any]) -> str:
    fields = (tx.get("date"), tx.get("type"), tx.get("amount_minor"), tx.get("comments"))
    return f"  row {index}: " + " | ".join("" if value is None else str(value) for value in fields)


def _report(rel: Path, added: Counter, unclassified: List[Tuple[int, Dict[str, Any]]], verb: str) -> None:
    if added:
        kinds = ", ".join(f"{kind} {count}" for kind, count in sorted(added.items()))
        print(f"{rel}: {sum(added.values())} row(s) {verb} ({kinds})")
    if unclassified:
        print(f"{rel}: {len(unclassified)} cash row(s) left unclassified")
        for index, tx in unclassified:
            print(_describe(index, tx))


def _report_layout(reformatted: List[Tuple[Path, bool]]) -> None:
    print(f"{len(reformatted)} file(s) whose layout would be reformatted (not in json.dumps indent=2 layout)")
    for rel, written in reformatted:
        status = "would be rewritten and reformatted" if written else "would be reformatted if written (not written)"
        print(f"  {rel}: {status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accounts_root", type=Path, help="Directory holding one folder per owner")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args(argv)

    if not args.accounts_root.is_dir():
        print(f"Not a directory: {args.accounts_root}", file=sys.stderr)
        return 2
    verb = "would be classified" if args.dry_run else "classified"
    total, left, kept = 0, 0, 0
    reformatted: List[Tuple[Path, bool]] = []
    for path in sorted(args.accounts_root.glob(f"*/*{_SUFFIX}")):
        rel = path.relative_to(args.accounts_root)
        added, unclassified, legacy, reformat = _process(path, args.dry_run)
        _report(rel, added, unclassified, verb)
        if legacy:
            print(f'{rel}: {legacy} row(s) with legacy kind "{_LEGACY_ACCOUNT_KIND}" left as is')
        total += sum(added.values())
        left += len(unclassified)
        kept += legacy
        if reformat:
            reformatted.append((rel, bool(added)))
    print(f"{total} row(s) {verb} in total; {left} cash row(s) left unclassified")
    print(f'{kept} row(s) with legacy kind "{_LEGACY_ACCOUNT_KIND}" left as is (not a cash classification)')
    if args.dry_run:
        _report_layout(reformatted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
