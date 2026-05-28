"""Utilities to update account holdings from broker CSV exports."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, List

from backend import importers
from backend.common import portfolio_loader
from backend.common.path_utils import safe_join
from backend.config import config


def _to_holding(tx: Any) -> dict[str, object]:
    cost = (tx.amount_minor or 0.0) / 100.0 if tx.amount_minor is not None else 0.0
    holding: dict[str, object] = {
        "ticker": tx.ticker,
        "units": tx.units or 0.0,
        "cost_basis_gbp": cost,
    }
    if tx.price is not None:
        holding["current_price_gbp"] = tx.price
    return holding


def update_from_csv(
    owner: str,
    account: str,
    provider: str,
    data: bytes,
) -> dict[str, str]:
    """Parse ``data`` from ``provider`` and update ``owner``/``account`` holdings.

    Returns a mapping containing the path to the written holdings file. A
    dictionary is returned instead of a plain string so callers (and tests)
    can easily extend the response with additional metadata in the future
    without changing the return type again.
    """

    transactions: List[Any] = importers.parse(provider, data)

    holdings = [_to_holding(t) for t in transactions if t.ticker]

    payload = {
        "owner": owner,
        "account_type": account,
        "currency": "GBP",
        "last_updated": date.today().isoformat(),
        "holdings": holdings,
    }

    try:
        base_dir = safe_join(Path(config.accounts_root), owner)
        acct_path = safe_join(base_dir, f"{account}.json")
    except ValueError as exc:
        raise ValueError(f"Invalid path component: {exc}") from exc
    base_dir.mkdir(parents=True, exist_ok=True)
    acct_path.write_text(json.dumps(payload, indent=2))

    try:
        portfolio_loader.rebuild_account_holdings(owner, account)
    except Exception:  # pragma: no cover - rebuild errors are non-fatal
        pass

    return {"path": str(acct_path)}
