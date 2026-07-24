"""Maps raw Moneyhub Open Banking API transaction records to AllotMint's ``Transaction``.

Field mapping follows the plan in ``docs/moneyhub-integration.md``. Moneyhub
is a cash/bank-account aggregator (Open Banking AISP data), not a brokerage
feed, so these map onto AllotMint's cash-movement transactions
(``kind="account"``) rather than share trades -- there is no
ticker/price/shares source field to populate.

This is distinct from :mod:`backend.importers.moneyhub`, which parses manual
Moneyhub CSV exports (#3426); this module maps the live API's JSON response
shape (#3425) instead. Both feed the same ``Transaction`` model and the same
shared :func:`backend.importers.dedupe_against_existing` helper.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from backend.routes.transactions import Transaction

# Per the design doc's open question: Moneyhub returns transactions in
# various lifecycle states. "pending" transactions are excluded here because
# they later settle under a different, "posted" Moneyhub id -- importing
# both would double-count the same real-world movement.
_EXCLUDED_STATUSES = frozenset({"pending"})


def _amount_minor(amount: Mapping[str, Any] | None) -> Optional[float]:
    """Convert Moneyhub's decimal major-unit amount to minor units (pence/cents)."""
    if not amount:
        return None
    value = amount.get("amount")
    if value is None:
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _currency(amount: Mapping[str, Any] | None) -> Optional[str]:
    if not amount:
        return None
    return amount.get("currency")


def map_transactions(
    raw: List[Dict[str, Any]],
    owner: str,
    *,
    account_id_map: Optional[Mapping[str, str]] = None,
) -> List[Transaction]:
    """Map raw Moneyhub transaction records into ``Transaction`` rows for ``owner``.

    ``account_id_map`` translates Moneyhub's own ``accountId`` values into
    AllotMint account slugs (per the design doc, no automatic correspondence
    exists between the two, so this is a one-time manual link per connected
    account); unmapped account ids fall through unchanged so callers can see
    what still needs linking rather than silently dropping the row.
    """
    account_id_map = account_id_map or {}
    transactions: List[Transaction] = []

    for item in raw:
        if (item.get("status") or "").lower() in _EXCLUDED_STATUSES:
            continue

        raw_account_id = item.get("accountId") or ""
        account = account_id_map.get(raw_account_id, raw_account_id)
        raw_id = item.get("id")

        transactions.append(
            Transaction(
                external_id=f"moneyhub:{raw_id}" if raw_id else None,
                owner=owner,
                account=account,
                date=item.get("date"),
                type=item.get("category"),
                kind="account",
                amount_minor=_amount_minor(item.get("amount")),
                currency=_currency(item.get("amount")),
                comments=item.get("description"),
                synthetic=False,
            )
        )

    return transactions
