from fastapi import APIRouter, Request

from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.common.user_config import UserConfig, load_user_config, save_user_config
from backend.config import config

router = APIRouter(prefix="/user-config", tags=["user-config"])

@handle_owner_not_found
async def get_user_config(owner: str, request: Request):
    try:
        cfg = load_user_config(owner, request.app.state.accounts_root)
    except FileNotFoundError:
        cfg = UserConfig(
            hold_days_min=config.hold_days_min,
            max_trades_per_month=config.max_trades_per_month,
            approval_exempt_types=config.approval_exempt_types or [],
            approval_exempt_tickers=config.approval_exempt_tickers or [],
        )
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
