from __future__ import annotations

import json
from datetime import datetime, date
from collections import defaultdict

from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.common import portfolio_loader
from backend.common import portfolio as portfolio_mod
from backend.config import config

router = APIRouter(tags=["transactions"])
log = logging.getLogger("transactions")


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
        except (OSError, json.JSONDecodeError):
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
    existed = tx_file.exists()
    if existed:
        try:
            data = json.loads(tx_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Failed to read %s: %s", tx_file, exc)
            data = {
                "owner": owner,
                "account_type": account.upper(),
                "currency": payload.get("currency", "GBP"),
                "last_updated": date.today().isoformat(),
                "transactions": [],
            }
    else:
        data = {
            "owner": owner,
            "account_type": account.upper(),
            "currency": payload.get("currency", "GBP"),
            "last_updated": date.today().isoformat(),
            "transactions": [],
        }
        acct_path = owner_dir / f"{account.lower()}.json"
        if acct_path.exists():
            try:
                acct_data = json.loads(acct_path.read_text())
                seed_date = acct_data.get("last_updated", date.today().isoformat())
                for h in acct_data.get("holdings", []):
                    ticker = h.get("ticker")
                    units = h.get("units")
                    if ticker and units:
                        data["transactions"].append(
                            {
                                "date": seed_date,
                                "type": "BUY",
                                "ticker": ticker,
                                "shares": units,
                            }
                        )
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Failed to seed transactions from %s: %s", acct_path, exc)

    tx_record = {k: v for k, v in payload.items() if k not in {"owner", "account"}}
    data.setdefault("transactions", []).append(tx_record)
    data["last_updated"] = date.today().isoformat()
    try:
        tx_file.write_text(json.dumps(data, indent=2))
    except OSError as exc:
        log.error("Failed to write transactions to %s: %s", tx_file, exc)
        raise HTTPException(status_code=500, detail="failed to write transaction")

    # Rebuild holdings and refresh portfolio snapshot
    portfolio_loader.rebuild_account_holdings(owner, account, Path(root))
    try:
        portfolio_mod.build_owner_portfolio(owner, Path(root))
    except FileNotFoundError as exc:
        log.warning("Portfolio rebuild failed: %s", exc)

    return {"status": "ok"}
