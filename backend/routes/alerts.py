from fastapi import APIRouter
from backend.common.alerts import get_recent_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("/")
async def alerts():
    """Return recent alert messages."""
    return get_recent_alerts()
