from fastapi import APIRouter

from backend.common.trade_metrics import load_and_compute_metrics

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/stats")
async def agent_stats():
    """Return basic trade statistics for dashboards."""
    return load_and_compute_metrics()
