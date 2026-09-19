#!/usr/bin/env python3
"""
convert_portfolio_xml_to_account_transactions.py

Extracts transactions (both cash *account-transaction* and share *portfolio-transaction*)
from a PortfolioPerformance-style XML file and saves **one JSON file per account**
containing an array of normalised transactions.

The output folder structure matches the existing *convert_portfolio_xml_to_input_files.py*
convention – e.g. `data/accounts/steve/ISA_transactions.json` – so it can drop
straight into the same pipeline.

By default, paths are read from ``backend.config`` (keys ``portfolio_xml_path`` and
``transactions_output_root``). Use ``--xml-path`` and ``--output-root`` to
override these values on the command line.

Usage
-----
    python convert_portfolio_xml_to_account_transactions.py \\
        [--xml-path path/to/investments.xml] \\
        [--output-root data/accounts]

Requires `pandas` (install with `pip install pandas`).
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

import defusedxml.ElementTree as ET
import pandas as pd

from backend.config import config
from backend.utils.positions import build_security_lookup

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


def _security_fields(security_ref: str | None, sec_meta: Mapping[str, Mapping[str, str]]) -> Dict[str, Any]:
    """Resolve a transaction's security reference to instrument metadata.

    A transaction carries no ticker of its own, only a reference to a
    ``<security>`` elsewhere in the document.  Without resolving it the output
    cannot be matched to an instrument at all, which is why consumers such as
    the trade-marker chart overlay saw no trades for any holding.

    An unresolved reference yields empty fields rather than a guess: emitting
    the raw reference as though it were a ticker would silently mis-attribute
    the trade to a non-existent instrument.
    """
    meta = sec_meta.get(security_ref or "", {})
    return {
        "ticker": meta.get("ticker") or None,
        "instrument_name": meta.get("name") or None,
        "isin": meta.get("isin") or None,
    }


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
        acc.get("id"): acc.findtext("name") or f"Account {acc.get('id')}" for acc in root.findall(".//accounts/account")
    }

    # Map security-id -> instrument metadata, so each transaction can carry the
    # ticker it refers to rather than only an opaque reference.
    sec_meta = build_security_lookup(root)

    records: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # (1) Cash-account transactions: <account-transaction>
    # ------------------------------------------------------------------
    for acc in root.findall(".//accounts/account"):
        acc_id = acc.get("id")
        acc_name = account_names[acc_id]

        for trx in acc.findall("./transactions/account-transaction"):
            security_ref = _get_ref(trx, "security")
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
                    "security_ref": security_ref,
                    **_security_fields(security_ref, sec_meta),
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
            security_ref = _get_ref(ptrx, "security")
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
                    "security_ref": security_ref,
                    **_security_fields(security_ref, sec_meta),
                    "shares": _safe_int(ptrx.findtext("shares")),
                }
            )

    return pd.DataFrame.from_records(records)


###############################################################################
# Output helpers
###############################################################################


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _clean_records(group: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert a frame to records with missing values as ``None``.

    pandas represents a missing value as ``float('nan')``, which ``json.dump``
    writes as the bare literal ``NaN``.  That is not valid JSON: Python's own
    loader accepts it, but ``JSON.parse`` and the frontend's schema validation
    reject it, so the field would break every consumer of the response.
    """
    return [
        {key: (None if _is_missing(value) else value) for key, value in record.items()}
        for record in group.to_dict(orient="records")
    ]


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
            "transactions": _clean_records(group.drop(columns=["owner", "account_type"])),
        }

        target_dir = Path(out_dir) / owner
        target_dir.mkdir(parents=True, exist_ok=True)
        json_path = target_dir / f"{account_type}_transactions.json"

        with json_path.open("w", encoding="utf-8") as fh:
            # allow_nan=False turns any remaining non-finite value into a loud
            # failure here rather than a file that silently fails to parse
            # downstream.
            json.dump(out, fh, indent=2, allow_nan=False)

        print(f"Wrote {json_path} ({len(group)} transactions)")


###############################################################################
# CLI entry-point
###############################################################################


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and normalise transactions per account")
    parser.add_argument(
        "--xml-path",
        default=config.portfolio_xml_path,
        help="Path to PortfolioPerformance XML file",
    )
    parser.add_argument(
        "--output-root",
        default=config.transactions_output_root,
        help="Directory where JSON files will be written",
    )
    args = parser.parse_args()

    xml = args.xml_path
    output_root = args.output_root

    if xml is None or output_root is None:
        parser.error("Both --xml-path and --output-root must be provided")

    df = extract_transactions_by_account(xml_path=xml)
    write_account_json(df, output_root)


if __name__ == "__main__":  # pragma: no cover
    main()
