"""Flag dividend refresh estimates that booked income already covers (#11086).

Walks ``<accounts root>/<owner>/*_transactions.json`` and applies
:func:`backend.common.dividend_attribution.mark_attribution_only` to each
account, so an estimated per-ticker ``DIVIDEND`` dated on or before the
account's latest ticker-less booked dividend (e.g. HL's "Transfer from Income
Account") is never counted as income twice. The dividend refresh bot does the
same on every run; this is for a data checkout edited by hand, and for the
one-off migration of rows written before the flag existed.

A file with flagged rows is rewritten whole with ``json.dumps`` (2-space
indent, key order as loaded, whether it ended with a newline kept). A file
already in that layout shows only the flagged rows in a diff; a hand-edited
file with other indentation or spacing is reformatted throughout. ``--dry-run``
lists which files would change without writing them, so check those files'
layout before a real run. Files with nothing to flag are not touched.

Usage::

    python -m scripts.mark_dividend_attribution /path/to/allotmint-data/accounts [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.common.dividend_attribution import mark_attribution_only


def _process(path: Path, dry_run: bool) -> int:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    transactions = data.get("transactions") if isinstance(data, dict) else None
    if not isinstance(transactions, list):
        return 0
    changed = mark_attribution_only([tx for tx in transactions if isinstance(tx, dict)])
    if changed and not dry_run:
        # Same layout as the data files (2-space indent), keeping whether the
        # file ended with a newline so only the flagged rows show in a diff.
        # Any other layout is normalised; see the module docstring.
        text = json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
        path.write_text(text, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accounts_root", type=Path, help="Directory holding one folder per owner")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args(argv)

    if not args.accounts_root.is_dir():
        print(f"Not a directory: {args.accounts_root}", file=sys.stderr)
        return 2
    verb = "would change" if args.dry_run else "changed"
    total = 0
    for path in sorted(args.accounts_root.glob("*/*_transactions.json")):
        changed = _process(path, args.dry_run)
        if changed:
            print(f"{path.relative_to(args.accounts_root)}: {changed} row(s) {verb}")
        total += changed
    print(f"{total} row(s) {verb} in total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
