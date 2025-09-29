"""API endpoints exposing portfolio performance metrics."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException

from backend.common import portfolio_utils
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.utils.pricing_dates import PricingDateCalculator

router = APIRouter(tags=["performance"])


def _resolve_as_of(as_of: str | None) -> dt.date | None:
    if not as_of:
        return None
    try:
        candidate = dt.date.fromisoformat(as_of)
    except ValueError as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail="Invalid as_of date") from exc
    if candidate > dt.date.today():
        raise HTTPException(status_code=400, detail="Date cannot be in the future")
    calc = PricingDateCalculator()
    return calc.resolve_weekday(candidate, forward=False)


@router.get("/performance/{owner}/alpha")
@handle_owner_not_found
async def owner_alpha(
    owner: str,
    benchmark: str = "VWRL.L",
    days: int = 365,
    as_of: str | None = None,
):
    """Return portfolio alpha vs. benchmark for ``owner``."""
    try:
        val, breakdown = portfolio_utils.compute_alpha_vs_benchmark(
            owner,
            benchmark,
            days,
            include_breakdown=True,
            pricing_date=_resolve_as_of(as_of),
        )
        response = {"owner": owner, "benchmark": benchmark, "alpha_vs_benchmark": val}
        response.update(breakdown)
        return response
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/tracking-error")
@handle_owner_not_found
async def owner_tracking_error(
    owner: str,
    benchmark: str = "VWRL.L",
    days: int = 365,
    as_of: str | None = None,
):
    """Return tracking error vs. benchmark for ``owner``."""
    try:
        val, breakdown = portfolio_utils.compute_tracking_error(
            owner,
            benchmark,
            days,
            include_breakdown=True,
            pricing_date=_resolve_as_of(as_of),
        )
        response = {"owner": owner, "benchmark": benchmark, "tracking_error": val}
        response.update(breakdown)
        return response
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/max-drawdown")
@handle_owner_not_found
async def owner_max_drawdown(owner: str, days: int = 365, as_of: str | None = None):
    """Return max drawdown for ``owner``."""
    try:
        val, breakdown = portfolio_utils.compute_max_drawdown(
            owner,
            days,
            include_breakdown=True,
            pricing_date=_resolve_as_of(as_of),
        )
        response = {"owner": owner, "max_drawdown": val}
        response.update(breakdown)
        return response
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/twr")
@handle_owner_not_found
async def owner_twr(owner: str, days: int = 365, as_of: str | None = None):
    """Return time-weighted return for ``owner``."""
    try:
        val = portfolio_utils.compute_time_weighted_return(
            owner, days, pricing_date=_resolve_as_of(as_of)
        )
        return {"owner": owner, "time_weighted_return": val}
    except FileNotFoundError:
        raise_owner_not_found()


@router.get("/performance/{owner}/xirr")
@handle_owner_not_found
async def owner_xirr(owner: str, days: int = 365, as_of: str | None = None):
    """Return XIRR for ``owner``."""
    try:
        val = portfolio_utils.compute_xirr(
            owner, days, pricing_date=_resolve_as_of(as_of)
        )
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
        result = portfolio_utils.compute_group_alpha_vs_benchmark(
            slug, benchmark, days, include_breakdown=True
        )
        if isinstance(result, tuple):
            val, breakdown = result
        else:
            val, breakdown = result, {}
        response = {"group": slug, "benchmark": benchmark, "alpha_vs_benchmark": val}
        response.update(breakdown)
        return response
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/tracking-error")
async def group_tracking_error(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return tracking error vs. benchmark for a group portfolio."""
    try:
        result = portfolio_utils.compute_group_tracking_error(
            slug, benchmark, days, include_breakdown=True
        )
        if isinstance(result, tuple):
            val, breakdown = result
        else:
            val, breakdown = result, {}
        response = {"group": slug, "benchmark": benchmark, "tracking_error": val}
        response.update(breakdown)
        return response
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/max-drawdown")
async def group_max_drawdown(slug: str, days: int = 365):
    """Return max drawdown for a group portfolio."""
    try:
        result = portfolio_utils.compute_group_max_drawdown(
            slug, days, include_breakdown=True
        )
        if isinstance(result, tuple):
            val, breakdown = result
        else:
            val, breakdown = result, {}
        response = {"group": slug, "max_drawdown": val}
        response.update(breakdown)
        return response
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance/{owner}")
async def performance(
    owner: str,
    days: int = 365,
    exclude_cash: bool = False,
    as_of: str | None = None,
):
    """Return portfolio performance metrics for ``owner``.

    Set ``exclude_cash`` to true to ignore cash holdings when reconstructing the
    return series.
    """
    try:
        result = portfolio_utils.compute_owner_performance(
            owner,
            days=days,
            include_cash=not exclude_cash,
            pricing_date=_resolve_as_of(as_of),
        )
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
