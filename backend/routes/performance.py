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
        breakdown = portfolio_utils.alpha_vs_benchmark_breakdown(owner, benchmark, days)
        return {"owner": owner, "benchmark": benchmark, **breakdown}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/tracking-error")
@handle_owner_not_found
async def owner_tracking_error(owner: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return tracking error vs. benchmark for ``owner``."""
    try:
        breakdown = portfolio_utils.tracking_error_breakdown(owner, benchmark, days)
        return {"owner": owner, "benchmark": benchmark, **breakdown}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/max-drawdown")
@handle_owner_not_found
async def owner_max_drawdown(owner: str, days: int = 365):
    """Return max drawdown for ``owner``."""
    try:
        breakdown = portfolio_utils.max_drawdown_breakdown(owner, days)
        return {"owner": owner, **breakdown}
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


@router.get("/performance/{owner}/holdings")
@handle_owner_not_found
async def owner_holdings(owner: str, date: str):
    """Return holding values for ``owner`` on a specific date."""
    try:
        rows = portfolio_utils.portfolio_value_breakdown(owner, date)
        return {"owner": owner, "date": date, "holdings": rows}
    except FileNotFoundError:
        raise_owner_not_found()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/performance-group/{slug}/alpha")
async def group_alpha(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return alpha vs. benchmark for a group portfolio."""
    try:
        breakdown = portfolio_utils.group_alpha_vs_benchmark_breakdown(
            slug, benchmark, days
        )
        return {"group": slug, "benchmark": benchmark, **breakdown}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/tracking-error")
async def group_tracking_error(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return tracking error vs. benchmark for a group portfolio."""
    try:
        breakdown = portfolio_utils.group_tracking_error_breakdown(
            slug, benchmark, days
        )
        return {"group": slug, "benchmark": benchmark, **breakdown}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/max-drawdown")
async def group_max_drawdown(slug: str, days: int = 365):
    """Return max drawdown for a group portfolio."""
    try:
        breakdown = portfolio_utils.group_max_drawdown_breakdown(slug, days)
        return {"group": slug, **breakdown}
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


@router.get("/returns/compare")
@handle_owner_not_found
async def compare_returns(owner: str, days: int = 365):
    """Return portfolio CAGR and cash APY for ``owner``."""
    try:
        cagr = portfolio_utils.compute_cagr(owner, days)
        cash_apy = portfolio_utils.compute_cash_apy(owner, days)
        return {"owner": owner, "cagr": cagr, "cash_apy": cash_apy}
    except FileNotFoundError:
        raise_owner_not_found()
