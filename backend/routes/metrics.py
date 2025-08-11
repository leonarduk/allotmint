"""API endpoints exposing portfolio metrics."""

from fastapi import APIRouter, HTTPException

from backend.common.metrics import compute_and_store_metrics, load_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics/{owner}")
async def get_metrics(owner: str):
    """Return turnover and holding-period metrics for ``owner``."""
    try:
        metrics = load_metrics(owner)
        if not metrics:
            metrics = compute_and_store_metrics(owner)
        return metrics
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
