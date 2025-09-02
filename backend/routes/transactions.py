from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import fcntl

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import config

router = APIRouter(tags=["transactions"])


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


_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_component(value: str, field: str) -> str:
    if not _SAFE_COMPONENT_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


@router.post("/transactions")
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

    return {"owner": owner, "account": account, **tx_data}


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

    txs = []
    for t in _load_all_transactions():
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
