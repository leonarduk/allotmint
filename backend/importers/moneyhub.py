"""Parser for Moneyhub manual CSV exports.

No real Moneyhub sample export was available when this was written (see
issue #3426), so the column layout below is a best-effort guess based on
Moneyhub's documented transaction fields: a stable per-transaction ``Id``,
``Date``, ``Amount``, ``Description``, ``Category`` and account identifiers.
Adjust the column names here once a real export is available to verify
against.
"""

from __future__ import annotations

import csv
import io
from typing import List

from backend.routes.transactions import Transaction


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse(data: bytes) -> List[Transaction]:
    """Parse a Moneyhub manual CSV export into transactions.

    Expected columns: ``Id``, ``Owner``, ``Account``, ``Date``, ``Amount``,
    ``Description``, ``Category``.
    """
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    transactions: List[Transaction] = []
    for row in reader:
        transactions.append(
            Transaction(
                external_id=(row.get("Id") or row.get("id") or "").strip() or None,
                owner=row.get("Owner") or row.get("owner") or "",
                account=row.get("Account") or row.get("account") or "",
                date=row.get("Date") or row.get("date"),
                type=row.get("Category") or row.get("category"),
                amount_minor=_to_float(row.get("Amount") or row.get("amount")),
                comments=row.get("Description") or row.get("description"),
            )
        )
    return transactions
