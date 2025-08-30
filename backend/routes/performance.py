from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.common import portfolio_utils

router = APIRouter(tags=["performance"])


@router.get("/performance/{owner}")
async def performance(owner: str, days: int = 365, exclude_cash: bool = False):
    """Return portfolio performance metrics for ``owner``.

    Set ``exclude_cash`` to true to ignore cash holdings when reconstructing the
    return series.
    """
    try:
        result = portfolio_utils.compute_owner_performance(
            owner, days=days, include_cash=not exclude_cash
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    return {"owner": owner, **result}
