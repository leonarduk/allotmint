"""API endpoints exposing portfolio metrics."""

from fastapi import APIRouter

from backend.common.metrics import compute_and_store_metrics, load_metrics
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(tags=["metrics"])


@router.get("/metrics/{owner}")
@handle_owner_not_found
async def get_metrics(owner: str):
    """Return turnover and holding-period metrics for ``owner``."""
    try:
        metrics = load_metrics(owner)
        if not metrics:
            metrics = compute_and_store_metrics(owner)
        return metrics
    except FileNotFoundError:
        raise_owner_not_found()
