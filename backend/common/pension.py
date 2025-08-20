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
from typing import Optional, Dict, Any

DEFAULT_ANNUITY_MULTIPLE = 20  # crude capitalisation proxy


def _age_from_dob(dob_str: Optional[str], today: Optional[dt.date] = None) -> Optional[float]:
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
