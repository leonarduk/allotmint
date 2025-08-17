from fastapi import APIRouter, Request

from backend.common import compliance
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(tags=["compliance"])


@router.get("/compliance/{owner}")
@handle_owner_not_found
async def compliance_for_owner(owner: str, request: Request):
    """Return compliance warnings for an owner."""
    try:
        return compliance.check_owner(owner, request.app.state.accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()
