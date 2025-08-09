#!/usr/bin/env python3
"""
convert_portfolio_xml_to_account_transactions.py

Extracts transactions (both cash *account-transaction* and share *portfolio-transaction*)
from a PortfolioPerformance-style XML file and saves **one JSON file per account**
containing an array of normalised transactions.

The output folder structure matches the existing *convert_portfolio_xml_to_input_files.py*
convention – e.g. `data/accounts/steve/ISA_transactions.json` – so it can drop
straight into the same pipeline.

Usage
-----
    python convert_portfolio_xml_to_account_transactions.py path/to/investments.xml data/accounts

Requires `pandas` (install with `pip install pandas`).
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

###############################################################################
# Helpers
###############################################################################

def _safe_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None

def _get_ref(elem: ET.Element, tag: str) -> str | None:
    tag_elem = elem.find(tag)
    return tag_elem.get("reference") if tag_elem is not None else None

def _normalise_account_name(name: str) -> Tuple[str, str]:
    """Split **"Steve ISA Cash" -> ("steve", "isa")**, used for output paths."""
    parts = name.strip().split()
    if len(parts) >= 2:
        return parts[0].lower(), parts[1].lower()
    return "unknown", "unknown"

###############################################################################
# Core extraction logic
###############################################################################

def extract_transactions_by_account(xml_path: str) -> pd.DataFrame:
    """Return *all* transactions as a DataFrame with an *account* column."""

    root = ET.parse(xml_path).getroot()

    # Map account-id -> account-name so we can resolve names later
    account_names: dict[str, str] = {
        acc.get("id"): acc.findtext("name") or f"Account {acc.get('id')}"
        for acc in root.findall(".//accounts/account")
    }

    records: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # (1) Cash-account transactions: <account-transaction>
    # ------------------------------------------------------------------
    for acc in root.findall(".//accounts/account"):
        acc_id = acc.get("id")
        acc_name = account_names[acc_id]

        for trx in acc.findall("./transactions/account-transaction"):
            records.append(
                {
                    "kind": "account",
                    "account_id": acc_id,
                    "account": acc_name,
                    "transaction_id": trx.get("id"),
                    "uuid": trx.findtext("uuid"),
                    "date": trx.findtext("date"),
                    "currency": trx.findtext("currencyCode"),
                    "amount_minor": _safe_int(trx.findtext("amount")),
                    "type": trx.findtext("type"),
                    "security_ref": _get_ref(trx, "security"),
                    "shares": _safe_int(trx.findtext("shares")),
                }
            )

    # ------------------------------------------------------------------
    # (2) Share-account transactions: <portfolio-transaction>
    # ------------------------------------------------------------------
    for portfolio in root.findall(".//portfolio"):
        ref_account_elem = portfolio.find("referenceAccount")
        if ref_account_elem is None:
            continue  # portfolio not tied to a cash account -> skip

        acc_id = ref_account_elem.get("reference")
        acc_name = account_names.get(acc_id, f"Account {acc_id}")

        for ptrx in portfolio.findall("./transactions/portfolio-transaction"):
            records.append(
                {
                    "kind": "portfolio",
                    "account_id": acc_id,
                    "account": acc_name,
                    "portfolio_id": portfolio.get("id"),
                    "portfolio": portfolio.findtext("name"),
                    "transaction_id": ptrx.get("id"),
                    "uuid": ptrx.findtext("uuid"),
                    "date": ptrx.findtext("date"),
                    "currency": ptrx.findtext("currencyCode"),
                    "amount_minor": _safe_int(ptrx.findtext("amount")),
                    "type": ptrx.findtext("type"),
                    "security_ref": _get_ref(ptrx, "security"),
                    "shares": _safe_int(ptrx.findtext("shares")),
                }
            )

    return pd.DataFrame.from_records(records)

###############################################################################
# Output helpers
###############################################################################

def write_account_json(df: pd.DataFrame, out_dir: str) -> None:
    """Write *one JSON file per account* mirroring holdings-generation structure."""

    today = datetime.today().date().isoformat()

    # Derive owner / account_type from the *account* column the same way the
    # existing holdings script does.
    df["owner"], df["account_type"] = zip(*df["account"].map(_normalise_account_name))

    for (owner, account_type), group in df.groupby(["owner", "account_type"]):
        out = {
            "owner": owner,
            "account_type": account_type.upper(),
            "currency": "GBP",  # Assumes single-currency books
            "last_updated": today,
            "transactions": group.drop(columns=["owner", "account_type"]).to_dict(orient="records"),
        }

        target_dir = Path(out_dir) / owner
        target_dir.mkdir(parents=True, exist_ok=True)
        json_path = target_dir / f"{account_type}_transactions.json"

        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)

        print(f"Wrote {json_path} ({len(group)} transactions)")

###############################################################################
# CLI entry-point
###############################################################################

def main() -> None:
    xml = "C:/workspaces/bitbucket/luk/data/portfolio/investments-with-id.xml"
    output_root = "C:/workspaces/github/allotmint/data/transactions"

    df = extract_transactions_by_account(xml_path=xml)
    write_account_json(df, output_root)

if __name__ == "__main__":
    main()
