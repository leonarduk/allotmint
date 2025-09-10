from fastapi import APIRouter, HTTPException, Query

from backend.common.data_loader import load_person_meta
from backend.common.portfolio import build_owner_portfolio
from backend.common.pension import (
    _age_from_dob,
    forecast_pension,
    state_pension_age_uk,
)

router = APIRouter(tags=["pension"])


@router.get("/pension/forecast")
def pension_forecast(
    owner: str = Query(..., description="Portfolio owner"),
    death_age: int = Query(..., ge=0),
    state_pension_annual: float | None = Query(None, ge=0),
    db_income_annual: float | None = Query(None, ge=0),
    db_normal_retirement_age: int | None = Query(None, ge=0),
    contribution_annual: float | None = Query(None, ge=0),
    investment_growth_pct: float = Query(5.0),
    desired_income_annual: float | None = Query(None, ge=0),
):
    meta = load_person_meta(owner)
    dob = meta.get("dob")
    current_age = _age_from_dob(dob)
    if current_age is None:
        raise HTTPException(status_code=400, detail="missing or invalid dob")

    retirement_age = state_pension_age_uk(dob)
    if death_age <= retirement_age:
        raise HTTPException(
            status_code=400, detail="death_age must exceed retirement_age"
        )

    db_pensions = []
    if db_income_annual is not None and db_normal_retirement_age is not None:
        db_pensions.append(
            {
                "annual_income_gbp": db_income_annual,
                "normal_retirement_age": db_normal_retirement_age,
            }
        )

    try:
        result = forecast_pension(
            dob=dob,
            retirement_age=retirement_age,
            death_age=death_age,
            db_pensions=db_pensions,
            state_pension_annual=state_pension_annual,
            contribution_annual=contribution_annual or 0.0,
            investment_growth_pct=investment_growth_pct,
            desired_income_annual=desired_income_annual,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    portfolio = build_owner_portfolio(owner)
    pension_pot = sum(
        a.get("value_estimate_gbp", 0.0)
        for a in portfolio.get("accounts", [])
        if str(a.get("account_type", "")).lower() == "sipp"
    )

    result.update(
        {
            "retirement_age": retirement_age,
            "current_age": current_age,
            "pension_pot_gbp": pension_pot,
        }
    )
    return result
