"""Find what still references a cached price series (issue #8449).

A series is *orphaned* when no holding, no transaction and no instrument
metadata record refers to its ``SYM.EX`` ticker. Only orphaned series may be
deleted from the Research page.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from backend.common.instruments import get_instrument_meta
from backend.data_quality.issues import iter_holdings

logger = logging.getLogger(__name__)


class ReferenceScanUnavailable(RuntimeError):
    """Raised when references cannot be enumerated, so deletion must fail closed."""


def _matches(value: Any, full_ticker: str) -> bool:
    return isinstance(value, str) and value.strip().upper() == full_ticker


def _holding_references(full_ticker: str, accounts_root: Path | None) -> list[dict[str, str]]:
    if accounts_root is None or not Path(accounts_root).exists():
        raise ReferenceScanUnavailable("Holdings cannot be scanned in this environment")
    return [
        {"kind": "holding", "owner": owner, "account": account}
        for owner, account, holding in iter_holdings(accounts_root)
        if _matches(holding.get("ticker"), full_ticker)
    ]


def _transaction_references(full_ticker: str, store: Any) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for owner, account, document in store.iter_transaction_documents():
        transactions = document.get("transactions")
        if not isinstance(transactions, list):
            continue
        if any(
            isinstance(tx, dict)
            and (_matches(tx.get("ticker"), full_ticker) or _matches(tx.get("security_ref"), full_ticker))
            for tx in transactions
        ):
            refs.append({"kind": "transaction", "owner": owner, "account": account})
    return refs


def find_series_references(
    ticker: str,
    exchange: str,
    *,
    accounts_root: Path | None,
    stores: Iterable[Any],
) -> dict[str, Any]:
    """Return ``{"references": [...], "has_metadata": bool, "orphaned": bool}``.

    ``references`` lists each owner/account holding or transaction document
    that mentions ``ticker.exchange``. Raises :class:`ReferenceScanUnavailable`
    when holdings cannot be scanned.
    """
    full_ticker = f"{ticker}.{exchange}".upper()
    references = _holding_references(full_ticker, accounts_root)
    for store in stores:
        references.extend(_transaction_references(full_ticker, store))
    has_metadata = bool(get_instrument_meta(full_ticker))
    return {
        "references": references,
        "has_metadata": has_metadata,
        "orphaned": not references and not has_metadata,
    }
