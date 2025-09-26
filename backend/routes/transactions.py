from __future__ import annotations

import json
import logging
import os
import platform
import re
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, TextIO

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
from fastapi import Request, UploadFile, File, Form
from pydantic import BaseModel, ConfigDict, Field

from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_loader
from backend.common.ticker_utils import normalise_filter_ticker
from backend.common import compliance
from backend.common.instruments import get_instrument_meta
from backend.config import config
from backend import importers
from backend.utils import update_holdings_from_csv

router = APIRouter(tags=["transactions"])
log = logging.getLogger("transactions")


class Transaction(BaseModel):
    """Simple representation of a transaction record."""

    owner: str
    account: str
    id: str | None = None
    date: str | None = None
    ticker: str | None = None
    type: str | None = None
    kind: str | None = None
    amount_minor: float | None = None
    currency: str | None = None
    security_ref: str | None = None
    price_gbp: float | None = None
    price: float | None = None
    shares: float | None = None
    units: float | None = None
    fees: float | None = None
    comments: str | None = None
    reason: str | None = None
    reason_to_buy: str | None = None
    synthetic: bool = False
    instrument_name: str | None = None

    model_config = ConfigDict(extra="ignore", allow_inf_nan=True)


_POSTED_TRANSACTIONS: List[dict] = []
_PORTFOLIO_IMPACT: defaultdict[str, float] = defaultdict(float)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ID_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_-]+):(?P<account>[A-Za-z0-9_-]+):(?P<index>\d+)$"
)


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


class TransactionUpdate(TransactionCreate):
    pass


def _build_transaction_id(owner: str, account: str, index: int) -> str:
    return f"{owner}:{account}:{index}"


def _parse_transaction_id(tx_id: str) -> Tuple[str, str, int]:
    match = _ID_RE.fullmatch(tx_id)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid transaction id")
    return (
        match.group("owner"),
        match.group("account"),
        int(match.group("index")),
    )


def _calculate_portfolio_impact(tx: Mapping[str, object]) -> float:
    try:
        price = float(tx.get("price_gbp") or 0.0)
        units = float(tx.get("units") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return price * units


def _as_non_empty_str(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _instrument_name_from_entry(entry: Mapping[str, Any]) -> str | None:
    for key in ("instrument_name", "name", "display_name"):
        existing = _as_non_empty_str(entry.get(key))
        if existing:
            return existing

    ticker_value = entry.get("ticker") or entry.get("security_ref")
    ticker = _as_non_empty_str(ticker_value)
    if not ticker:
        return None

    try:
        meta = get_instrument_meta(ticker.upper())
    except ValueError:
        return None
    except Exception:  # pragma: no cover - unexpected lookup failure
        log.debug("Failed to load instrument metadata for ticker %s", ticker)
        return None

    for key in ("name", "instrument_name", "display_name"):
        meta_name = _as_non_empty_str(meta.get(key))
        if meta_name:
            return meta_name
    return None


def _format_transaction_response(
    owner: str, account: str, tx_data: Mapping[str, Any], tx_id: Optional[str] = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"owner": owner, "account": account, **tx_data}
    if tx_id is not None:
        payload["id"] = tx_id

    name = _instrument_name_from_entry(payload)
    if name:
        payload["instrument_name"] = name
    return payload


def _prepare_updated_transaction(existing: Mapping[str, object], update: Mapping[str, object]) -> Dict[str, object]:
    managed_fields = {"ticker", "date", "price_gbp", "units", "fees", "comments", "reason"}
    updated = dict(existing)
    for field in managed_fields:
        if field not in update or update.get(field) is None:
            updated.pop(field, None)
    for key, value in update.items():
        if value is not None:
            updated[key] = value
    updated.pop("id", None)
    return updated


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
        account_raw = data.get("account_type") or path.stem.replace("_transactions", "")
        account = account_raw.lower()
        transactions = data.get("transactions", []) or []
        for idx, t in enumerate(transactions):
            t = dict(t)
            t.pop("account", None)
            instrument_name = _instrument_name_from_entry(t)
            if instrument_name:
                t["instrument_name"] = instrument_name
            results.append(
                Transaction(
                    owner=owner,
                    account=account,
                    id=_build_transaction_id(owner, account_raw, idx),
                    **t,
                )
            )
    return results


def _find_transaction_file(owner: str, account: str) -> Tuple[Path, str]:
    if not config.accounts_root:
        raise HTTPException(status_code=400, detail="Accounts root not configured")

    owner_dir = Path(config.accounts_root) / owner
    if not owner_dir.exists():
        raise HTTPException(status_code=404, detail="Transaction not found")

    account_lower = account.lower()
    for candidate in owner_dir.glob("*_transactions.json"):
        candidate_account = candidate.stem.replace("_transactions", "")
        if candidate_account.lower() == account_lower:
            return candidate, candidate_account
    raise HTTPException(status_code=404, detail="Transaction not found")


@contextmanager
def _locked_transactions_data(owner: str, account: str) -> Iterator[Tuple[dict, TextIO]]:
    owner_dir = Path(config.accounts_root) / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    file_path = owner_dir / f"{account}_transactions.json"
    mode = "r+" if file_path.exists() else "w+"
    with file_path.open(mode, encoding="utf-8") as f:
        _lock_file(f)
        f.seek(0)
        try:
            data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {"owner": owner, "account_type": account, "transactions": []}
        else:
            data.setdefault("owner", owner)
            data.setdefault("account_type", account)
            data.setdefault("transactions", [])
        yield data, f
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        _unlock_file(f)


def _rebuild_portfolio(owner: str, account: str) -> None:
    try:
        accounts_root = Path(config.accounts_root)
        if not config.offline_mode:
            portfolio_loader.rebuild_account_holdings(owner, account, accounts_root)
        portfolio_mod.build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError as exc:
        log.warning("Portfolio rebuild failed: %s", exc)


@router.get("/transactions/compliance")
async def transactions_with_compliance(
    owner: str,
    request: Request,
    account: Optional[str] = None,
    ticker: Optional[str] = None,
):
    """Return transactions for ``owner`` annotated with compliance warnings."""

    txs = [t.model_dump() for t in _load_all_transactions() if t.owner.lower() == owner.lower()]
    if account:
        txs = [
            t
            for t in txs
            if (t.get("account") or "").lower() == account.lower()
        ]
    norm_ticker = normalise_filter_ticker(
        ticker,
        offline_mode=bool(config.offline_mode),
        fallback=getattr(config, "offline_fundamentals_ticker", None),
    )
    if norm_ticker:
        txs = [t for t in txs if (t.get("ticker") or "").upper() == norm_ticker]
    txs.sort(key=lambda t: _parse_date(t.get("date")) or date.min)
    evaluated = compliance.evaluate_trades(owner, txs, request.app.state.accounts_root)
    return {"transactions": evaluated}


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

    with _locked_transactions_data(owner, account) as (data, _file):
        transactions = data.setdefault("transactions", [])
        transactions.append(tx_data)
        data["owner"] = owner
        data["account_type"] = account
        new_index = len(transactions) - 1

    _rebuild_portfolio(owner, account)

    tx_id = _build_transaction_id(owner, account, new_index)
    return _format_transaction_response(owner, account, tx_data, tx_id)


@router.put("/transactions/{tx_id}")
async def update_transaction(tx_id: str, tx: TransactionUpdate) -> dict:
    if not config.accounts_root:
        raise HTTPException(status_code=400, detail="Accounts root not configured")

    original_owner, original_account_raw, index = _parse_transaction_id(tx_id)
    original_owner = _validate_component(original_owner, "owner")
    original_account = _validate_component(original_account_raw, "account")

    tx_data = tx.model_dump(mode="json")
    new_owner = _validate_component(tx_data.pop("owner"), "owner")
    new_account = _validate_component(tx_data.pop("account"), "account")
    if not tx_data.get("reason"):
        raise HTTPException(status_code=400, detail="reason is required")

    _, original_account_canonical = _find_transaction_file(original_owner, original_account)

    same_owner = new_owner.lower() == original_owner.lower()
    same_account = new_account.lower() == original_account_canonical.lower()
    same_location = same_owner and same_account

    old_impact = 0.0
    new_entry: Dict[str, object]
    pending_entry: Optional[Dict[str, object]] = None

    with _locked_transactions_data(original_owner, original_account_canonical) as (data, _):
        transactions = data.setdefault("transactions", [])
        if index >= len(transactions) or index < 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
        existing = transactions[index]
        old_impact = _calculate_portfolio_impact(existing)

        if same_location:
            updated_entry = _prepare_updated_transaction(existing, tx_data)
            transactions[index] = updated_entry
            data["owner"] = new_owner
            data["account_type"] = new_account
            new_entry = updated_entry
        else:
            removed_entry = transactions.pop(index)
            data["owner"] = original_owner
            data["account_type"] = original_account_canonical
            pending_entry = _prepare_updated_transaction(removed_entry, tx_data)
            new_entry = pending_entry

    new_index = index

    if not same_location:
        if pending_entry is None:
            raise HTTPException(status_code=500, detail="Failed to update transaction")
        with _locked_transactions_data(new_owner, new_account) as (data, _):
            transactions = data.setdefault("transactions", [])
            transactions.append(pending_entry)
            data["owner"] = new_owner
            data["account_type"] = new_account
            new_index = len(transactions) - 1

    new_impact = _calculate_portfolio_impact(new_entry)

    if same_location:
        _PORTFOLIO_IMPACT[new_owner] += new_impact - old_impact
    else:
        _PORTFOLIO_IMPACT[original_owner] -= old_impact
        _PORTFOLIO_IMPACT[new_owner] += new_impact

    affected: List[Tuple[str, str]] = [(new_owner, new_account)]
    if not same_location:
        affected.append((original_owner, original_account_canonical))

    for owner_val, account_val in affected:
        _rebuild_portfolio(owner_val, account_val)

    new_id = _build_transaction_id(new_owner, new_account, new_index)
    account_response = new_account.lower()
    return _format_transaction_response(new_owner, account_response, new_entry, new_id)


@router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str) -> dict:
    if not config.accounts_root:
        raise HTTPException(status_code=400, detail="Accounts root not configured")

    owner, account_raw, index = _parse_transaction_id(tx_id)
    owner = _validate_component(owner, "owner")
    account = _validate_component(account_raw, "account")

    _, account_canonical = _find_transaction_file(owner, account)

    removed_entry: Optional[Mapping[str, object]] = None

    with _locked_transactions_data(owner, account_canonical) as (data, _):
        transactions = data.setdefault("transactions", [])
        if index >= len(transactions) or index < 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
        removed_entry = transactions.pop(index)
        data["owner"] = owner
        data["account_type"] = account_canonical

    if removed_entry is None:
        raise HTTPException(status_code=500, detail="Failed to delete transaction")

    impact = _calculate_portfolio_impact(removed_entry)
    _PORTFOLIO_IMPACT[owner] -= impact

    _rebuild_portfolio(owner, account_canonical)

    return {"status": "deleted"}


@router.post("/transactions/import", response_model=List[Transaction])
async def import_transactions(
    provider: str = Form(...), file: UploadFile = File(...)
) -> List[Transaction]:
    """Parse a transaction export and return the contained transactions."""

    data = await file.read()
    try:
        return importers.parse(provider, data)
    except importers.UnknownProvider as exc:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {exc}")
    except Exception as exc:  # pragma: no cover - parsing errors
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}")


@router.post("/holdings/import")
async def import_holdings(
    owner: str = Form(...),
    account: str = Form(...),
    provider: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Parse a holdings export and persist it to the accounts store.

    Returns a mapping containing the path of the written holdings file.
    """

    data = await file.read()
    try:
        return update_holdings_from_csv.update_from_csv(
            owner,
            account,
            provider,
            data,
        )
    except importers.UnknownProvider as exc:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {exc}")
    except Exception as exc:  # pragma: no cover - parsing errors
        raise HTTPException(status_code=400, detail=f"Failed to import file: {exc}")


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
    norm_ticker = normalise_filter_ticker(
        ticker,
        offline_mode=bool(config.offline_mode),
        fallback=getattr(config, "offline_fundamentals_ticker", None),
    )

    txs: List[Transaction] = []
    for t in _load_all_transactions():
        ttype = (t.type or "").upper()
        if ttype not in {"DIVIDEND", "DIVIDENDS"}:
            continue
        if owner and t.owner.lower() != owner.lower():
            continue
        if account and t.account.lower() != account.lower():
            continue
        if norm_ticker and (t.ticker or "").upper() != norm_ticker:
            continue
        tx_date = _parse_date(t.date)
        if start_d and (not tx_date or tx_date < start_d):
            continue
        if end_d and (not tx_date or tx_date > end_d):
            continue
        txs.append(t)

    return txs
