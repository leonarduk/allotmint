import json
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.common.approvals import delete_approval, load_approvals, upsert_approval
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(prefix="/accounts", tags=["approvals"])


def _resolve_owner_dir(root: Path, owner: str, *, require_exists: bool = False) -> Path:
    owner_dir = (root / owner).resolve()
    root_str = os.fspath(root)
    owner_str = os.fspath(owner_dir)
    if os.name == "nt":
        root_cmp = os.path.normcase(root_str)
        owner_cmp = os.path.normcase(owner_str)
    else:
        root_cmp = root_str
        owner_cmp = owner_str
    try:
        common = os.path.commonpath([root_cmp, owner_cmp])
    except ValueError:
        raise_owner_not_found()
    if common != root_cmp:
        raise_owner_not_found()
    if require_exists and not owner_dir.exists():
        raise_owner_not_found()
    return owner_dir


@router.get("/{owner}/approvals")
@handle_owner_not_found
async def get_approvals(owner: str, request: Request):
    root = Path(request.app.state.accounts_root).resolve()
    _resolve_owner_dir(root, owner)
    try:
        approvals = load_approvals(owner, root)
    except FileNotFoundError:
        approvals = {}
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}


@router.post("/{owner}/approval-requests")
@handle_owner_not_found
async def post_approval_request(owner: str, request: Request):
    data = await request.json()
    ticker = (data.get("ticker") or "").upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    root = Path(request.app.state.accounts_root).resolve()
    owner_dir = _resolve_owner_dir(root, owner, require_exists=True)
    path = owner_dir / "approval_requests.json"
    try:
        raw = json.loads(path.read_text())
        entries = raw.get("requests") if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            entries = []
    except Exception:
        entries = []
    entry = {"ticker": ticker, "requested_on": date.today().isoformat()}
    entries.append(entry)
    try:
        path.write_text(json.dumps({"requests": entries}, indent=2, sort_keys=True))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"requests": entries}


@router.post("/{owner}/approvals")
@handle_owner_not_found
async def post_approval(owner: str, request: Request):
    data = await request.json()
    ticker = (data.get("ticker") or "").upper()
    when = data.get("approved_on")
    if not when:
        raise HTTPException(status_code=400, detail="approved_on is required")
    try:
        approved_on = date.fromisoformat(when)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid approved_on") from exc
    root = Path(request.app.state.accounts_root).resolve()
    _resolve_owner_dir(root, owner, require_exists=True)
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
    root = Path(request.app.state.accounts_root).resolve()
    _resolve_owner_dir(root, owner, require_exists=True)
    approvals = delete_approval(owner, ticker, root)
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}
