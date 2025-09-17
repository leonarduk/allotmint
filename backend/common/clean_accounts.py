#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

# === CONFIG ===
REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
ACCOUNTS_DIR = REPO_ROOT / "data" / "accounts"
OVERWRITE = True  # set False to write to a new folder
# ==============

KEEP_FIELDS = {"ticker", "units", "cost_basis_gbp", "acquired_date"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def simplify_account_file(path: Path, out_dir: Path | None = None):
    acct = read_json(path)
    new_holdings = []
    for h in acct.get("holdings", []):
        simplified = {k: v for k, v in h.items() if k in KEEP_FIELDS}
        # Ensure missing keys still exist with None/0 defaults if you want consistency
        if "ticker" not in simplified:
            continue  # skip invalid
        simplified.setdefault("units", 0.0)
        simplified.setdefault("cost_basis_gbp", 0.0)
        new_holdings.append(simplified)
    acct["holdings"] = new_holdings

    if out_dir:
        out_path = out_dir / path.relative_to(ACCOUNTS_DIR)
    else:
        out_path = path

    write_json(out_path, acct)
    print(f"Simplified: {out_path}")


def main():
    out_dir = None
    if not OVERWRITE:
        out_dir = REPO_ROOT / "data" / "accounts_simplified"
    for file in ACCOUNTS_DIR.rglob("*.json"):
        simplify_account_file(file, out_dir)


if __name__ == "__main__":  # pragma: no cover
    main()
