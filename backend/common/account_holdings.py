"""Read an account's ``<account>.json`` holdings document.

Shared by ``GET /transactions`` (:mod:`backend.routes.transactions`) and the
reports (:mod:`backend.reports`), which both need the holdings the rebuild
writes so ticker-less trades resolve the same way on every path (#8122).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from backend.logging_setup import sanitise_log_value

if TYPE_CHECKING:
    from backend.common.accounts_store import LocalAccountsStore, S3AccountsStore

logger = logging.getLogger(__name__)


def normalise_account_file_name(account: str) -> str:
    return account.strip().lower()


def load_account_holdings_file(path: Path, owner: str, account: str) -> dict[str, Any]:
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable holdings %s: %s", sanitise_log_value(path), sanitise_log_value(exc))
            loaded = {}
    else:
        loaded = {}

    if not isinstance(loaded, dict):
        loaded = {}

    loaded.setdefault("owner", owner)
    loaded.setdefault("account_type", account)
    loaded.setdefault("currency", "GBP")
    holdings = loaded.get("holdings")
    if not isinstance(holdings, list):
        loaded["holdings"] = []
    return loaded


def read_store_holdings(
    store: Union["LocalAccountsStore", "S3AccountsStore"], owner: str, account: str
) -> Optional[Dict[str, Any]]:
    """Return ``account``'s ``<account>.json`` from ``store``, or ``None`` if it can't be read.

    Uses the file name the holdings rebuild writes (``account.lower()``). Only
    read paths call this, so an undecodable document is logged and treated as
    absent rather than failing the request (#8122).
    """
    filename = f"{normalise_account_file_name(account)}.json"
    try:
        return store.read_document(owner, filename)
    except (OSError, ValueError) as exc:
        logger.warning(
            "Ignoring unreadable holdings %s/%s: %s",
            sanitise_log_value(owner),
            sanitise_log_value(filename),
            sanitise_log_value(exc),
        )
        return None
