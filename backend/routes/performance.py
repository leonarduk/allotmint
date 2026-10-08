"""API endpoints exposing portfolio performance metrics."""

from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, HTTPException

from backend.common import portfolio_utils, risk_return
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.utils.pricing_dates import PricingDateCalculator

router = APIRouter(tags=["performance"])

_OWNER_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BENCHMARK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
# Benchmark tickers on the risk/return chart may be Yahoo index symbols (^FTSE).
_RISK_BENCHMARK_RE = re.compile(r"^\^?[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_MAX_RISK_RETURN_DAYS = 365 * 10


def _validate_owner_slug(value: str, field_name: str) -> str:
    candidate = (value or "").strip()
    if (
        not candidate
        or "/" in candidate
        or "\\" in candidate
        or ".." in candidate
        or not _OWNER_SLUG_RE.fullmatch(candidate)
    ):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return candidate


def _validate_benchmark(value: str) -> str:
    candidate = (value or "").strip().upper()
    if (
        not candidate
        or "/" in candidate
        or "\\" in candidate
        or ".." in candidate
        or not _BENCHMARK_RE.fullmatch(candidate)
    ):
        raise HTTPException(status_code=400, detail="Invalid benchmark")
    return candidate


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
def owner_alpha(
    owner: str,
    benchmark: str = "VWRL.L",
    days: int = 365,
    as_of: str | None = None,
):
    """Return portfolio alpha vs. benchmark for ``owner``."""
    owner = _validate_owner_slug(owner, "owner")
    benchmark = _validate_benchmark(benchmark)
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
        raise_owner_not_found(owner, benchmark=benchmark)


@router.get("/performance/{owner}/tracking-error")
@handle_owner_not_found
def owner_tracking_error(
    owner: str,
    benchmark: str = "VWRL.L",
    days: int = 365,
    as_of: str | None = None,
):
    """Return tracking error vs. benchmark for ``owner``."""
    owner = _validate_owner_slug(owner, "owner")
    benchmark = _validate_benchmark(benchmark)
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
        raise_owner_not_found(owner, benchmark=benchmark)


@router.get("/performance/{owner}/max-drawdown")
@handle_owner_not_found
def owner_max_drawdown(owner: str, days: int = 365, as_of: str | None = None):
    """Return max drawdown for ``owner``."""
    owner = _validate_owner_slug(owner, "owner")
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
        raise_owner_not_found(owner)


@router.get("/performance/{owner}/twr")
@handle_owner_not_found
def owner_twr(owner: str, days: int = 365, as_of: str | None = None):
    """Return time-weighted return for ``owner``."""
    owner = _validate_owner_slug(owner, "owner")
    try:
        val = portfolio_utils.compute_time_weighted_return(owner, days, pricing_date=_resolve_as_of(as_of))
        return {"owner": owner, "time_weighted_return": val}
    except FileNotFoundError:
        raise_owner_not_found(owner)


@router.get("/performance/{owner}/xirr")
@handle_owner_not_found
def owner_xirr(owner: str, days: int = 365, as_of: str | None = None):
    """Return XIRR for ``owner``."""
    owner = _validate_owner_slug(owner, "owner")
    try:
        val = portfolio_utils.compute_xirr(owner, days, pricing_date=_resolve_as_of(as_of))
        return {"owner": owner, "xirr": val}
    except FileNotFoundError:
        raise_owner_not_found(owner)


@router.get("/performance/{owner}/fx-attribution")
@handle_owner_not_found
def owner_fx_attribution(owner: str, days: int = 365, as_of: str | None = None):
    """Split ``owner``'s ledger P&L over the window into local, FX, income and other (#9804).

    The window matches ``/performance/{owner}/twr``. ``fx_attribution`` is
    ``None`` when the owner has no transaction ledger to rebuild. Cash is not
    attributed: the ledger books every cash amount in GBP, so FX on foreign
    cash balances is not modelled (``cash_fx_modelled: false``).
    """
    owner = _validate_owner_slug(owner, "owner")
    try:
        result = portfolio_utils.compute_fx_attribution(owner, days, pricing_date=_resolve_as_of(as_of))
        return {"owner": owner, "fx_attribution": result}
    except FileNotFoundError:
        raise_owner_not_found(owner)


@router.get("/performance/{owner}/holdings")
@handle_owner_not_found
def owner_holdings(owner: str, date: str):
    """Return holding values for ``owner`` on a specific date."""
    owner = _validate_owner_slug(owner, "owner")
    try:
        rows = portfolio_utils.portfolio_value_breakdown(owner, date)
        return {"owner": owner, "date": date, "holdings": rows}
    except FileNotFoundError:
        raise_owner_not_found(owner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/performance-group/{slug}/alpha")
def group_alpha(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return alpha vs. benchmark for a group portfolio."""
    slug = _validate_owner_slug(slug, "slug")
    benchmark = _validate_benchmark(benchmark)
    try:
        result = portfolio_utils.compute_group_alpha_vs_benchmark(slug, benchmark, days, include_breakdown=True)
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
def group_tracking_error(slug: str, benchmark: str = "VWRL.L", days: int = 365):
    """Return tracking error vs. benchmark for a group portfolio."""
    slug = _validate_owner_slug(slug, "slug")
    benchmark = _validate_benchmark(benchmark)
    try:
        result = portfolio_utils.compute_group_tracking_error(slug, benchmark, days, include_breakdown=True)
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
def group_max_drawdown(slug: str, days: int = 365):
    """Return max drawdown for a group portfolio."""
    slug = _validate_owner_slug(slug, "slug")
    try:
        result = portfolio_utils.compute_group_max_drawdown(slug, days, include_breakdown=True)
        if isinstance(result, tuple):
            val, breakdown = result
        else:
            val, breakdown = result, {}
        response = {"group": slug, "max_drawdown": val}
        response.update(breakdown)
        return response
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}")
def group_performance(
    slug: str,
    days: int = 365,
    exclude_cash: bool = False,
    as_of: str | None = None,
):
    """Return combined portfolio performance metrics for a group of owners.

    Mirrors ``/performance/{owner}`` but aggregates holdings across every
    member of the ``slug`` group (see ``/groups``) instead of a single
    owner. Set ``exclude_cash`` to true to ignore cash holdings when
    reconstructing the return series.
    """
    slug = _validate_owner_slug(slug, "slug")
    try:
        result = portfolio_utils.compute_owner_performance(
            slug,
            days=days,
            include_cash=not exclude_cash,
            pricing_date=_resolve_as_of(as_of),
            group=True,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    return {"group": slug, **result}


def _validate_risk_window(days: int) -> int:
    if days < 30 or days > _MAX_RISK_RETURN_DAYS:
        raise HTTPException(status_code=400, detail="days must be between 30 and 3650")
    return days


@router.get("/performance-group/{slug}/risk-return")
def group_risk_return(slug: str, days: int = 365, as_of: str | None = None):
    """Return and volatility for the group, each member and each of their accounts.

    Feeds the "Returns vs Volatility" dashboard chart. Figures are rebuilt
    from the transaction ledgers (see ``backend.common.risk_return``);
    members without a ledger are listed in ``missing_members``.
    """
    slug = _validate_owner_slug(slug, "slug")
    days = _validate_risk_window(days)
    try:
        return risk_return.compute_group_risk_return(slug, days, pricing_date=_resolve_as_of(as_of))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/risk-return/benchmark")
def benchmark_risk_return(ticker: str, days: int = 365, as_of: str | None = None):
    """Return and volatility of a benchmark index or ticker over ``days``."""
    candidate = (ticker or "").strip().upper()
    if ".." in candidate or not _RISK_BENCHMARK_RE.fullmatch(candidate):
        raise HTTPException(status_code=400, detail="Invalid ticker")
    days = _validate_risk_window(days)
    result = risk_return.compute_benchmark_risk_return(candidate, days, pricing_date=_resolve_as_of(as_of))
    if result is None:
        raise HTTPException(status_code=404, detail="No price history for ticker")
    return result


@router.get("/performance-group/{slug}/twr")
def group_twr(slug: str, days: int = 365, as_of: str | None = None):
    """Return the combined time-weighted return for a group portfolio.

    ``partial`` is true, and ``missing_members`` lists who, when at least
    one member's transaction ledger could not be found. The figure is
    rebuilt from the other members' pooled ledgers, so it leaves those
    members out (#9169); see ``compute_time_weighted_return`` for the
    fallback when no member has a ledger (#7228).
    """
    slug = _validate_owner_slug(slug, "slug")
    try:
        val, missing_members = portfolio_utils.compute_time_weighted_return(
            slug,
            days,
            pricing_date=_resolve_as_of(as_of),
            group=True,
            include_missing_members=True,
        )
        return {
            "group": slug,
            "time_weighted_return": val,
            "partial": bool(missing_members),
            "missing_members": missing_members,
        }
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance-group/{slug}/xirr")
def group_xirr(slug: str, days: int = 365, as_of: str | None = None):
    """Return the combined XIRR for a group portfolio.

    ``partial`` is true, and ``missing_members`` lists who, when at least
    one member's transaction ledger could not be found. The figure is
    rebuilt from the other members' pooled ledgers, so it leaves those
    members out (#9169); see ``compute_time_weighted_return`` for the
    fallback when no member has a ledger (#7228).
    """
    slug = _validate_owner_slug(slug, "slug")
    try:
        val, missing_members = portfolio_utils.compute_xirr(
            slug,
            days,
            pricing_date=_resolve_as_of(as_of),
            group=True,
            include_missing_members=True,
        )
        return {
            "group": slug,
            "xirr": val,
            "partial": bool(missing_members),
            "missing_members": missing_members,
        }
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc


@router.get("/performance/{owner}")
@handle_owner_not_found
def performance(
    owner: str,
    days: int = 365,
    exclude_cash: bool = False,
    as_of: str | None = None,
):
    """Return portfolio performance metrics for ``owner``.

    Set ``exclude_cash`` to true to ignore cash holdings when reconstructing the
    return series.
    """
    owner = _validate_owner_slug(owner, "owner")
    try:
        result = portfolio_utils.compute_owner_performance(
            owner,
            days=days,
            include_cash=not exclude_cash,
            pricing_date=_resolve_as_of(as_of),
        )
    except FileNotFoundError:
        raise_owner_not_found(owner)
    return {"owner": owner, **result}


@router.get("/returns/compare")
@handle_owner_not_found
def compare_returns(owner: str, days: int = 365):
    """Return portfolio CAGR and cash APY for ``owner``."""
    owner = _validate_owner_slug(owner, "owner")
    try:
        cagr = portfolio_utils.compute_cagr(owner, days)
        cash_apy = portfolio_utils.compute_cash_apy(owner, days)
        return {"owner": owner, "cagr": cagr, "cash_apy": cash_apy}
    except FileNotFoundError:
        raise_owner_not_found(owner)
