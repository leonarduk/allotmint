from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from backend import importers
from backend.common import compliance, data_loader
from backend.common.accounts_store import (
    LocalAccountsStore,
    S3AccountsStore,
)
from backend.common.instruments import get_instrument_meta
from backend.common.ticker_utils import normalise_filter_ticker
from backend.config import config
from backend.routes._accounts import resolve_accounts_root
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
_ID_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_-]+):(?P<account>[A-Za-z0-9_-]+):(?P<index>\d+)$")


AccountsStore = "LocalAccountsStore | S3AccountsStore"


def _resolve_local_root(request: Request) -> Tuple[Optional[Path], bool]:
    """Resolve the on-disk accounts root for ``request``.

    Returns ``(root, is_global)``.  ``root`` is ``None`` when no accounts root is
    configured at all (a genuine misconfiguration).  ``is_global`` is ``True``
    when the resolved root is the read-only shared/global demo dataset that
    writes must not mutate.
    """
    state_value = getattr(request.app.state, "accounts_root", None)
    state_is_global = getattr(request.app.state, "accounts_root_is_global", False)
    if state_value:
        try:
            state_path = Path(state_value).expanduser()
        except (TypeError, ValueError, OSError):
            state_path = None
        else:
            if state_path.exists() and not state_is_global:
                resolved_state = state_path.resolve()
                request.app.state.accounts_root = resolved_state
                request.app.state.accounts_root_is_global = False
                return resolved_state, False

    configured_root = getattr(config, "accounts_root", None)
    if not configured_root:
        return None, True

    try:
        configured_path = Path(configured_root).expanduser()
    except (TypeError, ValueError, OSError):
        return None, True

    if not configured_path.exists():
        return None, True

    try:
        global_root = data_loader.resolve_paths(None, None).accounts_root.resolve()
    except Exception:
        global_root = None
    else:
        try:
            configured_resolved = configured_path.resolve()
        except FileNotFoundError:
            configured_resolved = configured_path
        if global_root is not None and configured_resolved == global_root:
            return configured_resolved, True

    try:
        resolved = resolve_accounts_root(request)
    except FileNotFoundError:  # pragma: no cover - defensive
        return None, True

    if state_is_global or getattr(request.app.state, "accounts_root_is_global", False):
        return resolved, True

    if not resolved.exists():
        return resolved, True

    return resolved, False


def resolve_writable_store(request: Request) -> "AccountsStore":
    """Return the writable account-document store for ``request``.

    In the deployed AWS environment writes target a dedicated, non-global S3
    prefix (separate from the read-only ``accounts/`` demo data).  Locally the
    on-disk accounts root is used, flagged ``is_global`` when it resolves to the
    shared demo dataset so write handlers refuse to mutate it.
    """
    if getattr(config, "app_env", None) == "aws":
        bucket = os.getenv(data_loader.DATA_BUCKET_ENV)
        if bucket:
            return S3AccountsStore(bucket=bucket)
    root, is_global = _resolve_local_root(request)
    return LocalAccountsStore(root=root, is_global=is_global)


def _store_disabled_detail(store: "AccountsStore") -> str:
    """Return the 400 detail for a write against a non-writable store.

    Distinguishes a read-only-by-design store (resolves to the shared/global
    demo dataset) from a genuine misconfiguration (no real writable root).
    """
    local_root = getattr(store, "local_root", None)
    if local_root is not None:
        try:
            global_root = data_loader.resolve_paths(None, None).accounts_root.resolve()
        except Exception:
            global_root = None
        try:
            resolved_local = Path(local_root).resolve()
        except (TypeError, ValueError, OSError):
            resolved_local = None
        if global_root is not None and resolved_local == global_root:
            return (
                "Accounts store is read-only: it resolves to the shared demo "
                "dataset. Create an account to enable manual holdings and "
                "transaction writes."
            )
    return "Accounts root not configured"


def _require_writable_store(request: Request) -> "AccountsStore":
    """Resolve the writable store, raising a clear 400 when writes are disabled."""
    store = resolve_writable_store(request)
    if getattr(store, "is_global", False):
        raise HTTPException(status_code=400, detail=_store_disabled_detail(store))
    return store


def _global_accounts_root() -> Optional[Path]:
    """Return the read-only global/demo accounts root for read merges, if any."""
    for args in ((config.repo_root, config.accounts_root), (None, None)):
        try:
            root = data_loader.resolve_paths(*args).accounts_root
        except Exception:
            continue
        if root and root.exists():
            return root.resolve()
    return None


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


class ManualHoldingCreate(BaseModel):
    owner: str
    account: str
    ticker: str
    value_gbp: float | None = Field(default=None, gt=0)
    units: float | None = Field(default=None, gt=0)
    price_gbp: float | None = Field(default=None, gt=0)
    currency: str | None = None


class AccountCreate(BaseModel):
    owner: str
    account_type: str
    currency: str | None = None


def _normalise_account_file_name(account: str) -> str:
    return account.strip().lower()


# Metadata/scaffold files that live alongside account holdings JSON but are not
# themselves holdings accounts.
_NON_HOLDINGS_FILES = frozenset({"person.json", "settings.json", "approvals.json"})


def _is_non_holdings_file(name: str) -> bool:
    return name.endswith("_transactions.json") or name in _NON_HOLDINGS_FILES


def _load_account_holdings_file(path: Path, owner: str, account: str) -> dict[str, Any]:
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError, ValueError):
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


def _account_payload_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    account_type = str(payload.get("account_type") or "").strip()
    currency = str(payload.get("currency") or "GBP").strip().upper() or "GBP"
    holdings_raw = payload.get("holdings")
    holdings = holdings_raw if isinstance(holdings_raw, list) else []
    return {
        "account_type": account_type,
        "currency": currency,
        "holdings": holdings,
        "holding_count": len(holdings),
    }


def _validate_manual_holding_payload(payload: ManualHoldingCreate) -> None:
    has_value = payload.value_gbp is not None
    has_units = payload.units is not None
    has_price = payload.price_gbp is not None
    has_units_price = has_units and has_price
    has_partial_units_price = has_units != has_price
    if has_partial_units_price or has_value == has_units_price:
        raise HTTPException(
            status_code=400,
            detail="Provide either value_gbp or both units and price_gbp",
        )


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


def _transactions_from_doc(owner: str, account_raw: str, data: Mapping[str, Any]) -> List[Transaction]:
    results: List[Transaction] = []
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


def _load_all_transactions(store: Optional["AccountsStore"] = None) -> List[Transaction]:
    """Load transactions from the global demo dataset, overlaid by writable store.

    Writable documents take precedence over the read-only global dataset for the
    same ``(owner, account)`` so freshly written transactions are reflected in
    deployed read endpoints.
    """
    # files look like data/accounts/<owner>/<ACCOUNT>_transactions.json
    merged: Dict[Tuple[str, str], List[Transaction]] = {}

    if config.accounts_root:
        data_root = Path(config.accounts_root)
        if data_root.exists():
            for path in data_root.glob("*/*_transactions.json"):
                try:
                    data = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(data, dict):
                    continue
                owner = str(data.get("owner") or path.parent.name)
                account_raw = str(data.get("account_type") or path.stem.replace("_transactions", ""))
                merged[(owner.lower(), account_raw.lower())] = _transactions_from_doc(owner, account_raw, data)

    if store is not None:
        for owner, account_raw, data in store.iter_transaction_documents():
            merged[(owner.lower(), account_raw.lower())] = _transactions_from_doc(owner, account_raw, data)

    results: List[Transaction] = []
    for txs in merged.values():
        results.extend(txs)
    return results


def _find_transaction_account(owner: str, account: str, store: "AccountsStore") -> str:
    """Return the canonical account name for ``owner``'s transactions file.

    Looks in the writable store first, then falls back to the read-only global
    dataset.  Raises ``404`` when no matching transactions file exists.
    """
    account_lower = account.lower()
    suffix = "_transactions.json"
    for name in store.list_owner_files(owner):
        if not name.endswith(suffix):
            continue
        candidate_account = name[: -len(suffix)]
        if candidate_account.lower() == account_lower:
            return candidate_account

    global_root = _global_accounts_root()
    if global_root is not None:
        owner_dir = global_root / owner
        if owner_dir.exists():
            for candidate in owner_dir.glob("*_transactions.json"):
                candidate_account = candidate.stem.replace("_transactions", "")
                if candidate_account.lower() == account_lower:
                    return candidate_account

    raise HTTPException(status_code=404, detail="Transaction not found")


@contextmanager
def _locked_transactions_data(owner: str, account: str, store: "AccountsStore") -> Iterator[Tuple[dict, None]]:
    default = {"owner": owner, "account_type": account, "transactions": []}
    with store.edit_document(owner, f"{account}_transactions.json", default=default) as data:
        data.setdefault("owner", owner)
        data.setdefault("account_type", account)
        if not isinstance(data.get("transactions"), list):
            data["transactions"] = []
        yield data, None


@contextmanager
def _locked_account_holdings_data(
    owner: str, account: str, store: "AccountsStore"
) -> Iterator[Tuple[dict[str, Any], None]]:
    with store.edit_document(owner, f"{account}.json", default={}, trailing_newline=True) as data:
        data.setdefault("owner", owner)
        data.setdefault("account_type", account)
        data.setdefault("currency", "GBP")
        if not isinstance(data.get("holdings"), list):
            data["holdings"] = []
        yield data, None


def _rebuild_portfolio(owner: str, account: str, store: "AccountsStore") -> None:
    """Rebuild the holdings document for *owner*/*account* from its transactions.

    Delegates to the store-specific implementation so both local on-disk and
    S3-backed stores are handled correctly.
    """
    store.rebuild_portfolio(owner, account)


@router.get("/transactions/compliance")
async def transactions_with_compliance(
    owner: str,
    request: Request,
    account: Optional[str] = None,
    ticker: Optional[str] = None,
):
    """Return transactions for ``owner`` annotated with compliance warnings."""

    store = resolve_writable_store(request)
    txs = [t.model_dump() for t in _load_all_transactions(store) if t.owner.lower() == owner.lower()]
    if account:
        txs = [t for t in txs if (t.get("account") or "").lower() == account.lower()]
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
async def create_transaction(request: Request, tx: TransactionCreate) -> dict:
    """Store a new transaction and return it.

    If the owner does not yet have a writable account root, one is created
    implicitly via :meth:`~backend.common.accounts_store.AccountsStore.ensure_owner`.
    There is no separate account-creation endpoint; see
    :mod:`backend.common.signup_provision` for the admin-approval provisioning
    path that runs before any user write.
    """

    store = _require_writable_store(request)

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

    store.ensure_owner(owner)
    with _locked_transactions_data(owner, account, store) as (data, _file):
        transactions = data.setdefault("transactions", [])
        transactions.append(tx_data)
        data["owner"] = owner
        data["account_type"] = account
        new_index = len(transactions) - 1

    _rebuild_portfolio(owner, account, store)

    tx_id = _build_transaction_id(owner, account, new_index)
    return _format_transaction_response(owner, account, tx_data, tx_id)


@router.put("/transactions/{tx_id}")
async def update_transaction(request: Request, tx_id: str, tx: TransactionUpdate) -> dict:
    store = _require_writable_store(request)

    original_owner, original_account_raw, index = _parse_transaction_id(tx_id)
    original_owner = _validate_component(original_owner, "owner")
    original_account = _validate_component(original_account_raw, "account")

    tx_data = tx.model_dump(mode="json")
    new_owner = _validate_component(tx_data.pop("owner"), "owner")
    new_account = _validate_component(tx_data.pop("account"), "account")
    if not tx_data.get("reason"):
        raise HTTPException(status_code=400, detail="reason is required")

    original_account_canonical = _find_transaction_account(original_owner, original_account, store)

    same_owner = new_owner.lower() == original_owner.lower()
    same_account = new_account.lower() == original_account_canonical.lower()
    same_location = same_owner and same_account

    old_impact = 0.0
    new_entry: Dict[str, object]
    pending_entry: Optional[Dict[str, object]] = None

    store.ensure_owner(new_owner)
    with _locked_transactions_data(original_owner, original_account_canonical, store) as (data, _):
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
        with _locked_transactions_data(new_owner, new_account, store) as (data, _):
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
        _rebuild_portfolio(owner_val, account_val, store)

    new_id = _build_transaction_id(new_owner, new_account, new_index)
    account_response = new_account.lower()
    return _format_transaction_response(new_owner, account_response, new_entry, new_id)


@router.delete("/transactions/{tx_id}")
async def delete_transaction(request: Request, tx_id: str) -> dict:
    store = _require_writable_store(request)

    owner, account_raw, index = _parse_transaction_id(tx_id)
    owner = _validate_component(owner, "owner")
    account = _validate_component(account_raw, "account")

    account_canonical = _find_transaction_account(owner, account, store)

    removed_entry: Optional[Mapping[str, object]] = None

    with _locked_transactions_data(owner, account_canonical, store) as (data, _):
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

    _rebuild_portfolio(owner, account_canonical, store)

    return {"status": "deleted"}


@router.post("/transactions/import", response_model=List[Transaction])
async def import_transactions(provider: str = Form(...), file: UploadFile = File(...)) -> List[Transaction]:
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


@router.post("/holdings/manual")
async def create_manual_holding(request: Request, payload: ManualHoldingCreate) -> dict[str, Any]:
    """Create a manual holding for the authenticated owner.

    If the owner does not yet have a writable account root, one is created
    implicitly via :meth:`~backend.common.accounts_store.AccountsStore.ensure_owner`.
    There is no separate account-creation endpoint; see
    :mod:`backend.common.signup_provision` for the admin-approval provisioning
    path that runs before any user write.
    """
    _validate_manual_holding_payload(payload)
    owner = _validate_component(payload.owner, "owner")
    account = _validate_component(payload.account, "account")
    ticker = str(payload.ticker or "").strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    store = _require_writable_store(request)
    account_slug = _normalise_account_file_name(account)

    holding: dict[str, Any] = {"ticker": ticker}
    if payload.value_gbp is not None:
        holding["value_gbp"] = float(payload.value_gbp)
    else:
        holding["units"] = float(payload.units)
        holding["price"] = float(payload.price_gbp)

    store.ensure_owner(owner)
    with _locked_account_holdings_data(owner, account_slug, store) as (account_payload, _):
        if payload.currency:
            account_payload["currency"] = payload.currency.strip().upper() or "GBP"
        account_payload["last_updated"] = date.today().isoformat()
        account_payload["owner"] = owner
        account_payload["account_type"] = account_slug

        holdings = account_payload.setdefault("holdings", [])
        for index, existing in enumerate(holdings):
            existing_ticker = str(existing.get("ticker") or "").strip().upper() if isinstance(existing, Mapping) else ""
            if existing_ticker == ticker:
                holdings[index] = holding
                break
        else:
            holdings.append(holding)

    return {
        "status": "saved",
        "owner": owner,
        "account": account_slug,
        "holding": holding,
    }


@router.post("/accounts", status_code=201)
async def create_account(request: Request, payload: AccountCreate) -> dict[str, Any]:
    """Create an empty named portfolio account for ``payload.owner``.

    Produces a skeleton ``{account_type}.json`` document (owner, account_type,
    currency, empty holdings) without requiring a holding to be added first.
    Returns 409 if an account of that type already exists for the owner.
    """

    owner = _validate_component(payload.owner, "owner")
    account_type = _validate_component(payload.account_type, "account_type")
    account_slug = _normalise_account_file_name(account_type)
    filename = f"{account_slug}.json"
    if _is_non_holdings_file(filename):
        raise HTTPException(status_code=400, detail="Invalid account_type")

    store = _require_writable_store(request)

    if store.read_document(owner, filename) is not None:
        raise HTTPException(status_code=409, detail="Account already exists")

    store.ensure_owner(owner)
    currency = (payload.currency or "GBP").strip().upper() or "GBP"

    with _locked_account_holdings_data(owner, account_slug, store) as (account_payload, _):
        account_payload["owner"] = owner
        account_payload["account_type"] = account_slug
        account_payload["currency"] = currency
        account_payload["last_updated"] = date.today().isoformat()

    return {
        "status": "created",
        "owner": owner,
        "account": account_slug,
        "currency": currency,
    }


@router.get("/holdings/manual")
async def list_manual_holdings(
    request: Request,
    owner: str,
) -> dict[str, Any]:
    owner_name = _validate_component(owner, "owner")
    store = resolve_writable_store(request)

    # Merge the read-only global/demo dataset with the writable store, with
    # writable documents taking precedence per account slug.  Reads therefore
    # still surface demo content while reflecting any manual writes.
    summaries: dict[str, dict[str, Any]] = {}

    global_root = _global_accounts_root()
    if global_root is not None:
        owner_dir = global_root / owner_name
        if owner_dir.exists():
            for path in sorted(owner_dir.glob("*.json")):
                if _is_non_holdings_file(path.name):
                    continue
                payload = _load_account_holdings_file(path, owner_name, path.stem.lower())
                summaries[path.stem.lower()] = _account_payload_summary(payload)

    for name in store.list_owner_files(owner_name):
        if _is_non_holdings_file(name):
            continue
        slug = name[:-5].lower() if name.endswith(".json") else name.lower()
        doc = store.read_document(owner_name, name)
        if doc is None:
            continue
        doc.setdefault("owner", owner_name)
        doc.setdefault("account_type", slug)
        if not isinstance(doc.get("holdings"), list):
            doc["holdings"] = []
        summaries[slug] = _account_payload_summary(doc)

    accounts = [summaries[slug] for slug in sorted(summaries)]
    return {"owner": owner_name, "accounts": accounts}


@router.get("/transactions", response_model=List[Transaction])
async def list_transactions(
    request: Request,
    owner: Optional[str] = None,
    account: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    tx_type: Optional[str] = Query(None, alias="type"),
):
    """Return transactions with optional filtering."""

    start_d = _parse_date(start)
    end_d = _parse_date(end)

    store = resolve_writable_store(request)
    txs: List[Transaction] = []
    for t in _load_all_transactions(store):
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
    request: Request,
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

    store = resolve_writable_store(request)
    txs: List[Transaction] = []
    for t in _load_all_transactions(store):
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
