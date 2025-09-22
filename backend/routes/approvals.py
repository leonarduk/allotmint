import json
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.common import data_loader
from backend.common.approvals import delete_approval, load_approvals, upsert_approval
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.routes._accounts import resolve_accounts_root

router = APIRouter(prefix="/accounts", tags=["approvals"])


def _safe_owner_dir(root: Path, owner: str) -> Path | None:
    """Return ``owner``'s directory when it exists beneath ``root``."""

    resolved_root = root.expanduser().resolve()
    owner_dir = (resolved_root / owner).expanduser().resolve()
    root_path = os.path.abspath(os.fspath(resolved_root))
    owner_path = os.path.abspath(os.fspath(owner_dir))
    try:
        common = os.path.commonpath([root_path, owner_path])
    except ValueError:
        return None
    if os.name == "nt":
        if os.path.normcase(common) != os.path.normcase(root_path):
            return None
    elif common != root_path:
        return None
    if not owner_dir.exists():
        return None
    return owner_dir


def _resolve_owner_dir(root: Path, owner: str) -> Path:
    """Return ``owner``'s directory ensuring it is within ``root``.

    When the directory is not present under ``root`` the function falls back to
    the default accounts directory discovered via :func:`data_loader
    .resolve_paths`. This mirrors the behaviour of other routes which fall back
    to the bundled demo data when custom accounts are unavailable.
    """

    owner_dir = _safe_owner_dir(root, owner)
    if owner_dir:
        return owner_dir

    fallback_root = data_loader.resolve_paths(None, None).accounts_root
    if fallback_root:
        fallback_dir = _safe_owner_dir(fallback_root, owner)
        if fallback_dir:
            return fallback_dir

    raise_owner_not_found()


@router.get("/{owner}/approvals")
@handle_owner_not_found
async def get_approvals(owner: str, request: Request):
    root = resolve_accounts_root(request)
    owner_dir = _resolve_owner_dir(root, owner)
    effective_root = owner_dir.parent
    try:
        approvals = load_approvals(owner, effective_root)
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
    root = resolve_accounts_root(request)
    owner_dir = _resolve_owner_dir(root, owner)
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
    root = resolve_accounts_root(request)
    owner_dir = _resolve_owner_dir(root, owner)
    effective_root = owner_dir.parent
    approvals = upsert_approval(owner, ticker, approved_on, effective_root)
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}


@router.delete("/{owner}/approvals")
@handle_owner_not_found
async def delete_approval_route(owner: str, request: Request):
    data = await request.json()
    ticker = (data.get("ticker") or "").upper()
    root = resolve_accounts_root(request)
    owner_dir = _resolve_owner_dir(root, owner)
    effective_root = owner_dir.parent
    approvals = delete_approval(owner, ticker, effective_root)
    entries = [
        {"ticker": t, "approved_on": d.isoformat()} for t, d in approvals.items()
    ]
    return {"approvals": entries}
