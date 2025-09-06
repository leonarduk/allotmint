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
    args = parser.parse_args()

    url = f"{args.api.rstrip('/')}/transactions/import"
    with args.file.open("rb") as fh:
        files = {"file": (args.file.name, fh)}
        data = {"provider": args.provider}
        resp = requests.post(url, data=data, files=files, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - network errors
        print(f"Request failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(resp.json())


if __name__ == "__main__":
    main()
