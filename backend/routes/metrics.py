"""API endpoints exposing portfolio metrics."""

from typing import Optional

from fastapi import APIRouter, Depends, Request

from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.common.metrics import compute_and_store_metrics, load_metrics
from backend.routes._accounts import resolve_accounts_root

router = APIRouter(tags=["metrics"])


@router.get("/metrics/{owner}")
@handle_owner_not_found
def get_metrics(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    """Return turnover and holding-period metrics for ``owner``.

    The caller must be authorised for ``owner`` (:func:`ensure_owner_access`,
    #11346), checked before the metrics are loaded or computed and cached.
    """
    ensure_owner_access(identity, owner, resolve_accounts_root(request))
    try:
        metrics = load_metrics(owner)
        if not metrics:
            metrics = compute_and_store_metrics(owner)
        return metrics
    except FileNotFoundError:
        raise_owner_not_found(owner)
