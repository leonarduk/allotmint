from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from backend.config import config


class Transaction(BaseModel):
    """Simple representation of a transaction record."""

    owner: str
    account: str
    date: str | None = None
    ticker: str | None = None
    type: str | None = None
    amount_minor: int | None = None
    price: float | None = None
    units: float | None = None
    fees: float | None = None
    comments: str | None = None
    reason_to_buy: str | None = None

    model_config = ConfigDict(extra="allow")


router = APIRouter(tags=["transactions"])


def _load_all_transactions() -> List[Transaction]:
    results: List[Transaction] = []
    if not config.accounts_root:
        return results

    data_root = Path(config.accounts_root)
    if not data_root.exists():
        return results

    # files look like data/accounts/<owner>/<ACCOUNT>_transactions.json
    for path in data_root.glob("*/*_transactions.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        owner = data.get("owner", path.parent.name)
        account = data.get(
            "account_type", path.stem.replace("_transactions", "")
        )
        for t in data.get("transactions", []):
            results.append(Transaction(owner=owner, account=account, **t))
    return results


def _parse_date(d: Optional[str]) -> Optional[datetime.date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date()
    except ValueError:
        return None


@router.get("/transactions", response_model=List[Transaction])
async def list_transactions(
    owner: Optional[str] = None,
    account: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Return transactions with optional filtering."""

    start_d = _parse_date(start)
    end_d = _parse_date(end)

    txs: List[Transaction] = []
    for t in _load_all_transactions():
        if owner and t.owner.lower() != owner.lower():
            continue
        if account and t.account.lower() != account.lower():
            continue
        tx_date = _parse_date(t.date)
        if start_d and (not tx_date or tx_date < start_d):
            continue
        if end_d and (not tx_date or tx_date > end_d):
            continue
        txs.append(t)

    return txs
