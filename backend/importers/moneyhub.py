"""Parser for Moneyhub manual CSV exports.

No real Moneyhub sample export was available when this was written (see
issue #3426), so the column layout below is a best-effort guess based on
Moneyhub's documented transaction fields: ``Date``, ``Amount``,
``Description``, ``Category`` and account identifiers, plus an optional
per-row ``Id``. Adjust the column names here once a real export is
available to verify against.

Per issue #3426's guidance: a manual CSV export is not guaranteed to carry
a source-provided transaction id. When an ``Id`` column is present it is
used directly; otherwise a synthetic composite key is derived from
date+account+amount+description. The composite key can under-dedupe (two
genuinely distinct transactions sharing date/account/amount/description
collide) but that is the documented, accepted trade-off in the absence of
a real id -- see ``dedupe_against_existing`` in
``backend.importers``.
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


def _composite_key(date: str | None, account: str, amount: float | None, description: str | None) -> str | None:
    """Derive a synthetic dedupe key when no source-provided id is available.

    Returns ``None`` (no stable key) unless both ``date`` and ``amount`` are
    present, since those two fields carry the most identifying weight for a
    bank/aggregator transaction row.
    """
    if not date or amount is None:
        return None
    normalised_description = (description or "").strip().lower()
    return f"{date}|{account}|{amount:.2f}|{normalised_description}"


def parse(data: bytes) -> List[Transaction]:
    """Parse a Moneyhub manual CSV export into transactions.

    Expected columns: ``Owner``, ``Account``, ``Date``, ``Amount``,
    ``Description``, ``Category``, and optionally ``Id``.
    """
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    transactions: List[Transaction] = []
    for row in reader:
        account = row.get("Account") or row.get("account") or ""
        date = row.get("Date") or row.get("date")
        amount = _to_float(row.get("Amount") or row.get("amount"))
        description = row.get("Description") or row.get("description")
        row_id = (row.get("Id") or row.get("id") or "").strip() or None
        transactions.append(
            Transaction(
                external_id=row_id or _composite_key(date, account, amount, description),
                owner=row.get("Owner") or row.get("owner") or "",
                account=account,
                date=date,
                type=row.get("Category") or row.get("category"),
                amount_minor=amount,
                comments=description,
            )
        )
    return transactions
