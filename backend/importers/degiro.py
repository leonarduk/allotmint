"""Parser for DeGiro transaction exports."""

from __future__ import annotations

import csv
import io
from typing import List

from backend.routes.transactions import Transaction


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse(data: bytes) -> List[Transaction]:
    """Parse a CSV export from DeGiro into transactions."""
    text = data.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    transactions: List[Transaction] = []
    for row in reader:
        transactions.append(
            Transaction(
                owner=row.get("owner", ""),
                account=row.get("account", ""),
                date=row.get("date"),
                ticker=row.get("ticker"),
                type=row.get("type"),
                amount_minor=_to_float(row.get("amount_minor")),
                price=_to_float(row.get("price")),
                units=_to_float(row.get("units")),
                fees=_to_float(row.get("fees")),
                comments=row.get("comments"),
                reason_to_buy=row.get("reason_to_buy"),
            )
        )
    return transactions
