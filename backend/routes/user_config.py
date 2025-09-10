from fastapi import APIRouter, Request

from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.common.user_config import load_user_config, save_user_config

router = APIRouter(prefix="/user-config", tags=["user-config"])

@handle_owner_not_found
async def get_user_config(owner: str, request: Request):
    try:
        cfg = load_user_config(owner, request.app.state.accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()
    return cfg.to_dict()


@handle_owner_not_found
async def update_user_config(owner: str, request: Request):
    data = await request.json()
    try:
        save_user_config(owner, data, request.app.state.accounts_root)
        cfg = load_user_config(owner, request.app.state.accounts_root)
        return cfg.to_dict()
    except FileNotFoundError:
        raise_owner_not_found()


router.get("/{owner}")(get_user_config)
router.post("/{owner}")(update_user_config)
