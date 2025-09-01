from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from backend.common import portfolio_loader
from backend.common import portfolio as portfolio_mod
from backend.config import config

router = APIRouter(tags=["transactions"])


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


@router.post("/transactions")
async def add_transaction(payload: Dict[str, Any], request: Request):
    """Append a transaction and rebuild holdings for the affected account."""

    owner = (payload.get("owner") or "").strip()
    account = (payload.get("account") or "").strip()
    if not owner or not account:
        raise HTTPException(status_code=400, detail="owner and account are required")

    root = request.app.state.accounts_root or config.accounts_root
    owner_dir = Path(root) / owner
    owner_dir.mkdir(parents=True, exist_ok=True)

    tx_file = owner_dir / f"{account.lower()}_transactions.json"
    try:
        data = json.loads(tx_file.read_text()) if tx_file.exists() else {
            "owner": owner,
            "account_type": account.upper(),
            "currency": payload.get("currency", "GBP"),
            "last_updated": date.today().isoformat(),
            "transactions": [],
        }
    except Exception:
        data = {
            "owner": owner,
            "account_type": account.upper(),
            "currency": payload.get("currency", "GBP"),
            "last_updated": date.today().isoformat(),
            "transactions": [],
        }

    tx_record = {k: v for k, v in payload.items() if k not in {"owner", "account"}}
    data.setdefault("transactions", []).append(tx_record)
    data["last_updated"] = date.today().isoformat()
    tx_file.write_text(json.dumps(data, indent=2))

    # Rebuild holdings and refresh portfolio snapshot
    portfolio_loader.rebuild_account_holdings(owner, account, Path(root))
    try:
        portfolio_mod.build_owner_portfolio(owner, Path(root))
    except FileNotFoundError:
        pass

    return {"status": "ok"}
