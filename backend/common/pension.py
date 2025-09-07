from __future__ import annotations

"""
DB Pension utilities for AllotMint.

Given:
  - annual_income_gbp         # current statement £/yr
  - normal_retirement_age     # when income starts
  - current_age               # derived from person DOB (may be None)
  - assumed_cpi_pct           # annual inflation uplift to start
  - annuity_multiple          # simple capitalisation multiple (default 20x)

Returns dict with fields used in API response.
"""

import datetime as dt
from typing import Any, Dict, Optional

DEFAULT_ANNUITY_MULTIPLE = 20  # crude capitalisation proxy


def _age_from_dob(
    dob_str: Optional[str], today: Optional[dt.date] = None
) -> Optional[float]:
    """Convert YYYY-MM-DD string to fractional years age."""
    if not dob_str:
        return None
    today = today or dt.date.today()
    try:
        dob = dt.date.fromisoformat(dob_str)
    except ValueError:
        return None
    return (today - dob).days / 365.25


def estimate_db_pension_value(
    *,
    annual_income_gbp: float,
    normal_retirement_age: int,
    current_age: Optional[float],
    assumed_cpi_pct: float = 2.5,
    annuity_multiple: float = DEFAULT_ANNUITY_MULTIPLE,
    today: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """
    Estimate inflation-adjusted start income and a capital-equivalent value.

    NOTE: This is NOT advice; it's a modelling placeholder.
    """
    today = today or dt.date.today()

    if current_age is None:
        years_to_start = None
        income_at_start = annual_income_gbp  # unknown growth
    else:
        years_to_start = max(0.0, normal_retirement_age - current_age)
        if years_to_start > 0:
            growth = (1 + assumed_cpi_pct / 100.0) ** years_to_start
            income_at_start = annual_income_gbp * growth
        else:
            income_at_start = annual_income_gbp

    est_capital = income_at_start * annuity_multiple

    return {
        "today": today.isoformat(),
        "annual_income_now_gbp": annual_income_gbp,
        "current_age_years": current_age,
        "years_to_start": years_to_start,
        "income_at_start_gbp": income_at_start,
        "annuity_multiple_used": annuity_multiple,
        "est_capital_value_gbp": est_capital,
    }


def forecast_pension(
    *,
    dob: str,
    retirement_age: int,
    death_age: int,
    db_pensions: Optional[list[Dict[str, float]]] = None,
    state_pension_annual: Optional[float] = None,
    contribution_annual: float = 0.0,
    investment_growth_pct: float = 5.0,
    desired_income_annual: Optional[float] = None,
    annuity_multiple: float = DEFAULT_ANNUITY_MULTIPLE,
    today: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """Return a simple year-by-year pension income forecast.

    Each entry in ``db_pensions`` should contain ``annual_income_gbp`` and
    ``normal_retirement_age`` fields.  The state pension amount, if provided,
    is assumed to start at ``retirement_age``.  ``contribution_annual`` and
    ``investment_growth_pct`` are used to project the size of a defined
    contribution pot.  ``desired_income_annual`` is compared against the
    projected pot (via ``annuity_multiple``) to determine the earliest age
    that the desired income could be supported.

    The forecast runs from the current age (rounded down) up to but excluding
    ``death_age``.
    """

    today = today or dt.date.today()
    current_age = _age_from_dob(dob, today)
    if current_age is None:
        raise ValueError("Invalid dob")

    start_age = int(current_age)
    if death_age <= start_age:
        return {"forecast": [], "projected_pot_gbp": 0.0, "earliest_retirement_age": None}

    pensions = db_pensions or []
    forecast: list[Dict[str, float]] = []
    pot = 0.0
    pot_at_retirement = 0.0
    earliest_age: Optional[int] = None
    growth_factor = 1 + investment_growth_pct / 100.0
    for age in range(start_age, death_age):
        # update pot for the year
        if age < retirement_age:
            pot += contribution_annual
        pot *= growth_factor
        if age + 1 == retirement_age:
            pot_at_retirement = pot
        if desired_income_annual is not None and earliest_age is None:
            if pot / annuity_multiple >= desired_income_annual:
                earliest_age = age + 1

        # income forecast (defined benefit + state)
        income = 0.0
        if state_pension_annual is not None and age >= retirement_age:
            income += state_pension_annual
        for p in pensions:
            try:
                start = int(p.get("normal_retirement_age", retirement_age))
                if age >= start:
                    income += float(p.get("annual_income_gbp", 0.0))
            except Exception:
                continue
        forecast.append({"age": age, "income": income})

    return {
        "forecast": forecast,
        "projected_pot_gbp": pot_at_retirement,
        "earliest_retirement_age": earliest_age,
    }
