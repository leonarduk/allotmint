from fastapi import APIRouter, HTTPException, Query

from backend.common.pension import forecast_pension

router = APIRouter(tags=["pension"])


@router.get("/pension/forecast")
def pension_forecast(
    dob: str = Query(..., description="Date of birth YYYY-MM-DD"),
    retirement_age: int = Query(..., ge=0),
    death_age: int = Query(..., ge=0),
    state_pension_annual: float | None = Query(None, ge=0),
    db_income_annual: float | None = Query(None, ge=0),
    db_normal_retirement_age: int | None = Query(None, ge=0),
):
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
        forecast = forecast_pension(
            dob=dob,
            retirement_age=retirement_age,
            death_age=death_age,
            db_pensions=db_pensions,
            state_pension_annual=state_pension_annual,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"forecast": forecast}
