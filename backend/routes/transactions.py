from __future__ import annotations

import fcntl
import json
import logging
import os
import re
from datetime import date, datetime
from collections import defaultdict
from pathlib import Path
from typing import List, Optional
import fcntl

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.config import config


class Transaction(BaseModel):
    """Simple representation of a transaction record."""

    owner: str
    account: str
    date: str | None = None
    ticker: str | None = None
    type: str | None = None
    amount_minor: float | None = None
    price: float | None = None
    units: float | None = None
    fees: float | None = None
    comments: str | None = None
    reason_to_buy: str | None = None

    model_config = ConfigDict(extra="ignore", allow_inf_nan=True)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transactions"])

_POSTED_TRANSACTIONS: List[dict] = []
_PORTFOLIO_IMPACT: defaultdict[str, float] = defaultdict(float)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class TransactionCreate(BaseModel):
    owner: str
    account: str
    ticker: str
    date: date
    price: float
    units: float
    fees: Optional[float] = None
    comments: Optional[str] = None
    reason_to_buy: Optional[str] = None


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
            t = dict(t)
            t.pop("account", None)
            results.append(Transaction(owner=owner, account=account, **t))
    return results


def _parse_date(d: Optional[str]) -> Optional[datetime.date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date()
    except ValueError:
        return None


_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_component(value: str, field: str) -> str:
    if not _SAFE_COMPONENT_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


@router.post("/transactions", status_code=201)
async def create_transaction(tx: TransactionCreate) -> dict:
    """Store a new transaction and return it."""

    if not config.accounts_root:
        raise HTTPException(status_code=400, detail="Accounts root not configured")

    tx_data = tx.model_dump(mode="json")
    owner = _validate_component(tx_data.pop("owner"), "owner")
    account = _validate_component(tx_data.pop("account"), "account")

    owner_dir = Path(config.accounts_root) / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    file_path = owner_dir / f"{account}_transactions.json"

    with file_path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            logging.warning("Failed to parse existing transactions file %s: %s", file_path, exc)
            data = {"owner": owner, "account_type": account, "transactions": []}
        except OSError as exc:
            logging.warning("Failed to read transactions file %s: %s", file_path, exc)
            data = {"owner": owner, "account_type": account, "transactions": []}

        transactions = data.setdefault("transactions", [])
        transactions.append(tx_data)
        data["owner"] = owner
        data["account_type"] = account

        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)
# =======
#     owner = _validate_name(tx_data.pop("owner"), "owner")
#     account = _validate_name(tx_data.pop("account"), "account")

#     file_path = Path(config.accounts_root) / owner / f"{account}_transactions.json"
#     file_path.parent.mkdir(parents=True, exist_ok=True)

#     try:
#         with open(file_path, "a+") as f:
#             fcntl.flock(f.fileno(), fcntl.LOCK_EX)
#             try:
#                 f.seek(0)
#                 try:
#                     data = json.load(f)
#                 except json.JSONDecodeError as exc:
#                     logger.warning("Failed to parse %s: %s", file_path, exc)
#                     data = {"owner": owner, "account_type": account, "transactions": []}
#                 transactions = data.setdefault("transactions", [])
#                 transactions.append(tx_data)
#                 data["owner"] = owner
#                 data["account_type"] = account
#                 f.seek(0)
#                 json.dump(data, f, indent=2)
#                 f.truncate()
#                 f.flush()
#                 os.fsync(f.fileno())
#             finally:
#                 fcntl.flock(f.fileno(), fcntl.LOCK_UN)
#     except OSError as exc:
#         logger.error("Failed to write transaction file %s: %s", file_path, exc)
#         raise HTTPException(status_code=500, detail="Failed to save transaction") from exc

    return {"owner": owner, "account": account, **tx_data}


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
