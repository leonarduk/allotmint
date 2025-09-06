from __future__ import annotations

import json
import logging
import os
import platform
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

try:  # Unix-like systems
    import fcntl  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
    if platform.system() == "Windows":
        import msvcrt  # type: ignore
    else:  # pragma: no cover - unsupported platform
        raise
else:  # pragma: no cover - Unix
    msvcrt = None  # type: ignore[assignment]

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_loader
from backend.config import config

router = APIRouter(tags=["transactions"])
log = logging.getLogger("transactions")


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


def _lock_file(f) -> None:
    """Lock ``f`` for exclusive access."""
    if fcntl:
        fcntl.flock(f, fcntl.LOCK_EX)
    else:  # pragma: no cover - Windows
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 0x7FFFFFFF)


def _unlock_file(f) -> None:
    """Unlock ``f``."""
    if fcntl:
        fcntl.flock(f, fcntl.LOCK_UN)
    else:  # pragma: no cover - Windows
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 0x7FFFFFFF)


class TransactionCreate(BaseModel):
    owner: str
    account: str
    ticker: str
    date: date
    price_gbp: float = Field(gt=0)
    units: float = Field(gt=0)
    fees: Optional[float] = None
    comments: Optional[str] = None
    reason: Optional[str] = None


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
        except (OSError, json.JSONDecodeError):
            continue
        owner = data.get("owner", path.parent.name)
        account = data.get("account_type", path.stem.replace("_transactions", ""))
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
    if not tx_data.get("reason"):
        raise HTTPException(status_code=400, detail="reason is required")

    price = tx_data.get("price_gbp")
    units_val = tx_data.get("units")
    if price is None or units_val is None:
        raise HTTPException(status_code=400, detail="price_gbp and units are required")
    impact = float(price) * float(units_val)
    _PORTFOLIO_IMPACT[owner] += impact
    _POSTED_TRANSACTIONS.append({"owner": owner, "account": account, **tx_data})

    owner_dir = Path(config.accounts_root) / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    file_path = owner_dir / f"{account}_transactions.json"

    with file_path.open("a+", encoding="utf-8") as f:
        _lock_file(f)
        f.seek(0)
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            log.warning("Failed to parse existing transactions file %s: %s", file_path, exc)
            data = {"owner": owner, "account_type": account, "transactions": []}
        except OSError as exc:
            log.warning("Failed to read transactions file %s: %s", file_path, exc)
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
        _unlock_file(f)

    try:
        accounts_root = Path(config.accounts_root)
        if not config.offline_mode:
            portfolio_loader.rebuild_account_holdings(owner, account, accounts_root)
        portfolio_mod.build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError as exc:
        log.warning("Portfolio rebuild failed: %s", exc)

    return {"owner": owner, "account": account, **tx_data}


@router.get("/transactions", response_model=List[Transaction])
async def list_transactions(
    owner: Optional[str] = None,
    account: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    tx_type: Optional[str] = Query(None, alias="type"),
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
        if tx_type and (t.type or "").upper() != tx_type.upper():
            continue
        tx_date = _parse_date(t.date)
        if start_d and (not tx_date or tx_date < start_d):
            continue
        if end_d and (not tx_date or tx_date > end_d):
            continue
        txs.append(t)

    return txs


@router.get("/dividends", response_model=List[Transaction])
async def list_dividends(
    owner: Optional[str] = None,
    account: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    ticker: Optional[str] = None,
):
    """Return only dividend transactions, grouped per owner/instrument."""

    start_d = _parse_date(start)
    end_d = _parse_date(end)

    txs: List[Transaction] = []
    for t in _load_all_transactions():
        ttype = (t.type or "").upper()
        if ttype not in {"DIVIDEND", "DIVIDENDS"}:
            continue
        if owner and t.owner.lower() != owner.lower():
            continue
        if account and t.account.lower() != account.lower():
            continue
        if ticker and (t.ticker or "").lower() != ticker.lower():
            continue
        tx_date = _parse_date(t.date)
        if start_d and (not tx_date or tx_date < start_d):
            continue
        if end_d and (not tx_date or tx_date > end_d):
            continue
        txs.append(t)

    return txs
