"""API endpoints exposing portfolio performance metrics."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.common import portfolio_utils
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(tags=["performance"])


@router.get("/performance/{owner}/alpha")
@handle_owner_not_found
async def owner_alpha(owner: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return portfolio alpha vs. benchmark for ``owner``."""
    try:
        val = portfolio_utils.compute_alpha_vs_benchmark(owner, benchmark, days)
        return {"owner": owner, "benchmark": benchmark, "alpha_vs_benchmark": val}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/tracking-error")
@handle_owner_not_found
async def owner_tracking_error(owner: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return tracking error vs. benchmark for ``owner``."""
    try:
        val = portfolio_utils.compute_tracking_error(owner, benchmark, days)
        return {"owner": owner, "benchmark": benchmark, "tracking_error": val}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/max-drawdown")
@handle_owner_not_found
async def owner_max_drawdown(owner: str, days: int = 365):
    """Return max drawdown for ``owner``."""
    try:
        val = portfolio_utils.compute_max_drawdown(owner, days)
        return {"owner": owner, "max_drawdown": val}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/twr")
@handle_owner_not_found
async def owner_twr(owner: str, days: int = 365):
    """Return time-weighted return for ``owner``."""
    try:
        val = portfolio_utils.compute_time_weighted_return(owner, days)
        return {"owner": owner, "time_weighted_return": val}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/xirr")
@handle_owner_not_found
async def owner_xirr(owner: str, days: int = 365):
    """Return XIRR for ``owner``."""
    try:
        val = portfolio_utils.compute_xirr(owner, days)
        return {"owner": owner, "xirr": val}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance-group/{slug}/alpha")
async def group_alpha(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return alpha vs. benchmark for a group portfolio."""
    try:
        val = portfolio_utils.compute_group_alpha_vs_benchmark(slug, benchmark, days)
        return {"group": slug, "benchmark": benchmark, "alpha_vs_benchmark": val}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/tracking-error")
async def group_tracking_error(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return tracking error vs. benchmark for a group portfolio."""
    try:
        val = portfolio_utils.compute_group_tracking_error(slug, benchmark, days)
        return {"group": slug, "benchmark": benchmark, "tracking_error": val}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/max-drawdown")
async def group_max_drawdown(slug: str, days: int = 365):
    """Return max drawdown for a group portfolio."""
    try:
        val = portfolio_utils.compute_group_max_drawdown(slug, days)
        return {"group": slug, "max_drawdown": val}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance/{owner}")
async def performance(owner: str, days: int = 365, exclude_cash: bool = False):
    """Return portfolio performance metrics for ``owner``.

    Set ``exclude_cash`` to true to ignore cash holdings when reconstructing the
    return series.
    """
    try:
        result = portfolio_utils.compute_owner_performance(owner, days=days, include_cash=not exclude_cash)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    return {"owner": owner, **result}
