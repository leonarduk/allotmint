import inspect

from fastapi import APIRouter, HTTPException, Query, Request

from backend.common.data_loader import load_person_meta
from backend.common.pension import (
    _age_from_dob,
    forecast_pension,
    state_pension_age_uk,
)
from backend.common.portfolio import build_owner_portfolio
from backend.routes._accounts import resolve_accounts_root

# Lower-case substrings that indicate a defined contribution account whose value
# should be treated as part of the pension pot.  New data files should stick to
# one of these identifiers (e.g. "sipp" or vendor-prefixed variants such as
# "kz:sipp") so that they are included automatically.
DEFINED_CONTRIBUTION_ACCOUNT_MARKERS = ("sipp",)

router = APIRouter(tags=["pension"])


@router.get("/pension/forecast")
def pension_forecast(
    request: Request,
    owner: str = Query(..., description="Portfolio owner"),
    death_age: int = Query(..., ge=0),
    state_pension_annual: float | None = Query(None, ge=0),
    db_income_annual: float | None = Query(None, ge=0),
    db_normal_retirement_age: int | None = Query(None, ge=0),
    contribution_annual: float | None = Query(None, ge=0),
    contribution_monthly: float | None = Query(None, ge=0),
    investment_growth_pct: float = Query(5.0),
    desired_income_annual: float | None = Query(None, ge=0),
):
    accounts_root = resolve_accounts_root(request)

    meta = load_person_meta(owner, accounts_root)
    dob = meta.get("dob")
    current_age = _age_from_dob(dob)
    if current_age is None:
        raise HTTPException(status_code=400, detail="missing or invalid dob")

    retirement_age = state_pension_age_uk(dob)
    if death_age <= retirement_age:
        raise HTTPException(status_code=400, detail="death_age must exceed retirement_age")

    # Keep the simulated forecast slightly beyond retirement to align with the
    # downstream planner assumptions even when the caller supplies a minimal
    # valid death age.
    forecast_death_age = max(death_age, retirement_age + 1)

    try:
        signature = inspect.signature(build_owner_portfolio)
    except (TypeError, ValueError):
        signature = None

    if signature and "root" in signature.parameters:
        kwargs: dict[str, object] = {"root": accounts_root}
    elif signature and "accounts_root" in signature.parameters:
        kwargs = {"accounts_root": accounts_root}
    else:
        kwargs = {"root": accounts_root}

    try:
        portfolio = build_owner_portfolio(owner, **kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pension_pot = 0.0
    for account in portfolio.get("accounts", []):
        account_type = str(account.get("account_type", "")).lower()
        if any(marker in account_type for marker in DEFINED_CONTRIBUTION_ACCOUNT_MARKERS):
            pension_pot += float(account.get("value_estimate_gbp") or 0.0)

    db_pensions = []
    if db_income_annual is not None and db_normal_retirement_age is not None:
        db_pensions.append(
            {
                "annual_income_gbp": db_income_annual,
                "normal_retirement_age": db_normal_retirement_age,
            }
        )

    annual_contribution = (
        (contribution_monthly or 0.0) * 12
        if contribution_monthly is not None
        else contribution_annual or 0.0
    )

    try:
        result = forecast_pension(
            dob=dob,
            retirement_age=retirement_age,
            death_age=forecast_death_age,
            db_pensions=db_pensions,
            state_pension_annual=state_pension_annual,
            contribution_annual=annual_contribution,
            investment_growth_pct=investment_growth_pct,
            desired_income_annual=desired_income_annual,
            initial_pot=pension_pot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result.update(
        {
            "retirement_age": retirement_age,
            "current_age": current_age,
            "dob": dob,
            "pension_pot_gbp": pension_pot,
        }
    )
    return result
