"""Parser for Hargreaves Lansdown holdings exports."""

from __future__ import annotations

import csv
import io
from typing import List

from backend.routes.transactions import Transaction


def _to_float(value: str | None) -> float | None:
    """Convert a string to float, ignoring commas and blanks."""
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse(data: bytes) -> List[Transaction]:
    """Parse a CSV export from Hargreaves Lansdown into holdings.

    The export contains columns such as ``Code``, ``Units held``,
    ``Price (pence)`` and ``Cost (£)``.  Prices in pence are converted to
    pounds and costs in pounds are scaled to ``amount_minor`` (pence).
    """

    text = data.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    transactions: List[Transaction] = []
    for row in reader:
        code = (row.get("Code") or row.get("code") or "").strip()
        units = _to_float(row.get("Units held") or row.get("Units"))
        price_pence = _to_float(row.get("Price (pence)") or row.get("Price"))
        price = price_pence / 100 if price_pence is not None else None
        cost = _to_float(row.get("Cost (£)") or row.get("Cost"))
        amount_minor = cost * 100 if cost is not None else None
        transactions.append(
            Transaction(
                owner="",
                account="",
                ticker=code or None,
                price=price,
                units=units,
                amount_minor=amount_minor,
            )
        )
    return transactions
