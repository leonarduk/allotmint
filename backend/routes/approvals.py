from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request

from backend.common.approvals import delete_approval, load_approvals, upsert_approval
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(prefix="/accounts", tags=["approvals"])


@router.get("/{owner}/approvals")
@handle_owner_not_found
async def get_approvals(owner: str, request: Request):
    root = request.app.state.accounts_root
    owner_dir = Path(root) / owner
    if not owner_dir.exists():
        raise_owner_not_found()
    approvals = load_approvals(owner, root)
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}


@router.post("/{owner}/approvals")
@handle_owner_not_found
async def post_approval(owner: str, request: Request):
    data = await request.json()
    ticker = (data.get("ticker") or "").upper()
    when = data.get("approved_on")
    approved_on = date.fromisoformat(when) if when else date.today()
    root = request.app.state.accounts_root
    owner_dir = Path(root) / owner
    if not owner_dir.exists():
        raise_owner_not_found()
    approvals = upsert_approval(owner, ticker, approved_on, root)
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}


@router.delete("/{owner}/approvals")
@handle_owner_not_found
async def delete_approval_route(owner: str, request: Request):
    data = await request.json()
    ticker = (data.get("ticker") or "").upper()
    root = request.app.state.accounts_root
    owner_dir = Path(root) / owner
    if not owner_dir.exists():
        raise_owner_not_found()
    approvals = delete_approval(owner, ticker, root)
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}
