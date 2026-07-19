"""CLI helper to import transaction files via the API."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload transactions for parsing")
    parser.add_argument("provider", help="Data provider name, e.g. degiro")
    parser.add_argument("file", type=Path, help="CSV/PDF file to upload")
    parser.add_argument(
        "--api", default="http://localhost:8000", help="Base URL of the backend API"
    )
    parser.add_argument(
        "--owner",
        default=None,
        help=(
            "Fallback owner for rows that don't carry their own (e.g. "
            "Hargreaves exports never set owner/account; degiro/moneyhub "
            "usually do). Rows with no resolvable owner/account are reported "
            "under 'skipped' rather than persisted (#4965)."
        ),
    )
    parser.add_argument(
        "--account", default=None, help="Fallback account for rows that don't carry their own."
    )
    args = parser.parse_args()

    url = f"{args.api.rstrip('/')}/transactions/import"
    with args.file.open("rb") as fh:
        files = {"file": (args.file.name, fh)}
        data = {"provider": args.provider}
        if args.owner:
            data["owner"] = args.owner
        if args.account:
            data["account"] = args.account
        resp = requests.post(url, data=data, files=files, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - network errors
        print(f"Request failed: {exc}", file=sys.stderr)
        sys.exit(1)
    result = resp.json()
    print(f"Persisted {len(result['persisted'])} transaction(s).")
    if result["skipped"]:
        print(f"Skipped {len(result['skipped'])} row(s):", file=sys.stderr)
        for row in result["skipped"]:
            print(f"  {row.get('skip_reason')}: {row}", file=sys.stderr)


if __name__ == "__main__":
    main()
