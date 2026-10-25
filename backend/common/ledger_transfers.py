"""Transfers that bring an account's ledger to a set number of units.

Holdings are rebuilt from each account's transactions, so any path that sets a
holding's units directly (the manual-holding form, a holdings CSV import) also
records the ``TRANSFER_IN``/``TRANSFER_OUT`` that makes the replayed ledger
agree. Without it, the next transaction write rebuilds the holding from the
ledger and the change is lost (#10917).
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional

from backend.common.holdings_rebuild import drop_future_dated, name_aliases, replay_transactions

if TYPE_CHECKING:
    from backend.common.accounts_store import LocalAccountsStore, S3AccountsStore

OPENING_BALANCE_REASON = "Opening balance from holdings input"
SET_HOLDING_REASON = "Set holding from holdings input"
CSV_IMPORT_REASON = "Units change from holdings CSV import"
TRANSACTIONS_SUFFIX = "_transactions.json"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def replayed_units(transactions: List[Mapping[str, Any]], holdings: List[Mapping[str, Any]], ticker: str) -> float:
    """``ticker``'s units after replaying ``transactions`` as the rebuild does.

    Uses the rebuild's own replay (including its name -> ticker aliases), so
    an offset computed from it agrees with the rebuilt holding, including
    leaving out future-dated rows.
    """
    transactions = drop_future_dated(transactions, warn=False)
    aliases = name_aliases(transactions, holdings)
    position = replay_transactions(transactions, aliases=aliases, warn=False).positions.get(ticker)
    return position.units if position else 0.0


def offset_transaction(
    transactions: List[Mapping[str, Any]],
    holdings: List[Mapping[str, Any]],
    ticker: str,
    units: float,
    price: Optional[float],
    tx_date: Optional[str] = None,
    *,
    reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """The transaction that makes ``ticker``'s replayed units equal ``units``, or None if they already do.

    With ``tx_date`` the transaction is dated then (the user's choice).
    Without it, an increase is an opening-balance TRANSFER_IN dated at the
    account's oldest transaction, so it reads as a balance held from the
    start, and a decrease is a TRANSFER_OUT dated today: dated earlier, it
    could exceed the units held on that date, and the rebuild would ignore
    the excess.

    ``reason`` overrides the default (``SET_HOLDING_REASON`` with a date,
    else ``OPENING_BALANCE_REASON``). With no ``price`` the transfer carries
    none, so its units have unknown cost and the rebuild keeps the holding's
    stored ``cost_basis_gbp`` while the units agree.
    """
    delta = round(units - replayed_units(transactions, holdings, ticker), 8)
    if abs(delta) < 1e-8:
        return None
    today = date.today().isoformat()
    if tx_date:
        when, default_reason = tx_date, SET_HOLDING_REASON
    elif delta > 0:
        dates = sorted(
            str(t.get("date") or "")[:10] for t in transactions if _ISO_DATE.match(str(t.get("date") or "")[:10])
        )
        when, default_reason = (dates[0] if dates else today), OPENING_BALANCE_REASON
    else:
        when, default_reason = today, OPENING_BALANCE_REASON
    tx: Dict[str, Any] = {
        "type": "TRANSFER_IN" if delta > 0 else "TRANSFER_OUT",
        "ticker": ticker,
        "date": when,
        "units": abs(delta),
    }
    if price is not None:
        tx["price_gbp"] = price
    tx["reason"] = reason or default_reason
    return tx


def find_transactions_account(store: "LocalAccountsStore | S3AccountsStore", owner: str, account: str) -> Optional[str]:
    """The spelling of ``owner``'s existing ``<account>_transactions.json`` in ``store``, matched case-insensitively."""
    account_lower = account.lower()
    for name in store.list_owner_files(owner):
        if name.endswith(TRANSACTIONS_SUFFIX) and name[: -len(TRANSACTIONS_SUFFIX)].lower() == account_lower:
            return name[: -len(TRANSACTIONS_SUFFIX)]
    return None
