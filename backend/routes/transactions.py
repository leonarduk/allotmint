from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import config

router = APIRouter(tags=["transactions"])


# In-memory store for posted transactions used by tests. In a production
# setting transactions would be persisted to a database or object store but
# keeping them locally keeps the API side-effect free for the existing data
# fixtures while still allowing integration tests to exercise the route.
_POSTED_TRANSACTIONS: List[dict] = []
_PORTFOLIO_IMPACT = defaultdict(float)


class Transaction(BaseModel):
    """Simple model describing a portfolio transaction."""

    owner: str
    account: str
    ticker: str
    units: float
    price_gbp: float
    date: str
    reason: str


def _load_all_transactions() -> List[dict]:
    results: List[dict] = []
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
        account = data.get("account_type", path.stem.replace("_transactions", ""))
        for t in data.get("transactions", []):
            results.append({"owner": owner, "account": account, **t})
    return results


def _parse_date(d: Optional[str]) -> Optional[datetime.date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date()
    except ValueError:
        return None


@router.get("/transactions")
async def list_transactions(
    owner: Optional[str] = None,
    account: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Return transactions with optional filtering."""

    start_d = _parse_date(start)
    end_d = _parse_date(end)

    txs: List[dict] = []
    for t in _load_all_transactions() + _POSTED_TRANSACTIONS:
        if owner and t.get("owner", "").lower() != owner.lower():
            continue
        if account and t.get("account", "").lower() != account.lower():
            continue
        date_str = t.get("date")
        tx_date = _parse_date(date_str)
        if start_d and (not tx_date or tx_date < start_d):
            continue
        if end_d and (not tx_date or tx_date > end_d):
            continue
        txs.append(t)

    return txs


@router.post("/transactions", status_code=201)
async def post_transaction(tx: Transaction):
    """Record a new transaction.

    Validation is handled by :class:`Transaction`. Posted transactions are
    stored in memory so tests can verify persistence via the GET endpoint and
    portfolio updates without touching the fixture data on disk.
    """

    # Basic validation of fields that require custom checks
    if not _parse_date(tx.date):
        raise HTTPException(status_code=422, detail="Invalid date")
    if tx.units <= 0:
        raise HTTPException(status_code=422, detail="Units must be positive")
    if not tx.reason:
        raise HTTPException(status_code=422, detail="Reason required")

    data = tx.dict()
    _POSTED_TRANSACTIONS.append(data)
    _PORTFOLIO_IMPACT[tx.owner] += tx.units * tx.price_gbp
    return {"status": "ok", "transaction": data}
