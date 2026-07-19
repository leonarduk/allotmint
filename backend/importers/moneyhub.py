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

# Columns a Moneyhub export must have for a row to carry a meaningful
# transaction. ``Id`` and ``Description``/``Category`` are intentionally
# excluded: ``Id`` is optional (falls back to the composite key below) and
# the fixture/real exports this was reverse-engineered from omit it, while
# description/category can legitimately be blank on a real row. Matched
# case-insensitively against the normalised (lowercased) header row.
REQUIRED_COLUMNS = frozenset({"owner", "account", "date", "amount"})


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
    ``Description``, ``Category``, and optionally ``Id``. Header matching is
    case-insensitive, so ``ID``, ``id``, and ``iD`` are all accepted.

    Raises:
        ValueError: if any of ``REQUIRED_COLUMNS`` is missing from the
            header row (case-insensitively), e.g. a non-Moneyhub CSV was
            uploaded by mistake.
    """
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    normalised_fieldnames = [(name or "").strip().lower() for name in reader.fieldnames or []]
    missing = REQUIRED_COLUMNS - set(normalised_fieldnames)
    if missing:
        raise ValueError(
            f"CSV missing required columns: {', '.join(sorted(missing))}. "
            f"Expected columns: {', '.join(sorted(REQUIRED_COLUMNS))}"
        )
    reader.fieldnames = normalised_fieldnames

    transactions: List[Transaction] = []
    for row in reader:
        account = row.get("account") or ""
        date = row.get("date")
        amount = _to_float(row.get("amount"))
        description = row.get("description")
        row_id = (row.get("id") or "").strip() or None
        transactions.append(
            Transaction(
                external_id=row_id or _composite_key(date, account, amount, description),
                owner=row.get("owner") or "",
                account=account,
                date=date,
                type=row.get("category"),
                amount_minor=amount,
                comments=description,
            )
        )
    return transactions
