from fastapi import APIRouter, HTTPException

from backend.common import compliance

router = APIRouter(tags=["compliance"])


@router.get("/compliance/{owner}")
async def compliance_for_owner(owner: str):
    """Return compliance warnings for an owner."""
    try:
        return compliance.check_owner(owner)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
