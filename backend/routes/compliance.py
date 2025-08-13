from fastapi import APIRouter

from backend.common import compliance
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(tags=["compliance"])


@router.get("/compliance/{owner}")
@handle_owner_not_found
async def compliance_for_owner(owner: str):
    """Return compliance warnings for an owner."""
    try:
        return compliance.check_owner(owner)
    except FileNotFoundError:
        raise_owner_not_found()
