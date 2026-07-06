from fastapi import APIRouter, Depends, Request

from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.common.user_config import load_user_config, save_user_config
from backend.routes._accounts import resolve_accounts_root

router = APIRouter(prefix="/user-config", tags=["user-config"])


@handle_owner_not_found
async def get_user_config(owner: str, request: Request, identity: str | None = Depends(get_active_user)):
    accounts_root = resolve_accounts_root(request, allow_missing=True)
    ensure_owner_access(identity, owner, accounts_root)
    try:
        cfg = load_user_config(owner, accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()
    return cfg.to_dict()


@handle_owner_not_found
async def update_user_config(owner: str, request: Request, identity: str | None = Depends(get_active_user)):
    accounts_root = resolve_accounts_root(request, allow_missing=True)
    ensure_owner_access(identity, owner, accounts_root)
    data = await request.json()
    try:
        save_user_config(owner, data, accounts_root)
        cfg = load_user_config(owner, accounts_root)
        return cfg.to_dict()
    except FileNotFoundError:
        raise_owner_not_found()


router.get("/{owner}")(get_user_config)
router.post("/{owner}")(update_user_config)
