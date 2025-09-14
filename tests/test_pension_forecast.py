import datetime as dt

import datetime as dt

from backend.common.pension import forecast_pension


def test_forecast_pre_retirement_without_state():
    today = dt.date(2024, 1, 1)
    res = forecast_pension(
        dob="1984-01-01",
        retirement_age=65,
        death_age=70,
        db_pensions=[{"annual_income_gbp": 10000, "normal_retirement_age": 65}],
        today=today,
    )
    forecast = res["forecast"]
    assert forecast[0]["age"] == 40
    assert forecast[0]["income"] == 0
    assert forecast[25]["age"] == 65
    assert forecast[25]["income"] == 10000
    assert len(forecast) == 30


def test_forecast_pre_retirement_with_state():
    today = dt.date(2024, 1, 1)
    res = forecast_pension(
        dob="1984-01-01",
        retirement_age=65,
        death_age=70,
        db_pensions=[{"annual_income_gbp": 10000, "normal_retirement_age": 65}],
        state_pension_annual=9000,
        today=today,
    )
    assert res["forecast"][25]["income"] == 19000


def test_forecast_post_retirement_life_expectancy():
    today = dt.date(2024, 1, 1)
    res = forecast_pension(
        dob="1950-01-01",
        retirement_age=65,
        death_age=90,
        db_pensions=[{"annual_income_gbp": 10000, "normal_retirement_age": 65}],
        state_pension_annual=9000,
        today=today,
    )
    forecast = res["forecast"]
    assert forecast[0]["age"] == 73
    assert len(forecast) == 17
    assert all(r["income"] == 19000 for r in forecast)


def test_forecast_includes_initial_pot():
    today = dt.date(2024, 1, 1)
    res = forecast_pension(
        dob="1984-01-01",
        retirement_age=65,
        death_age=66,
        contribution_annual=0.0,
        investment_growth_pct=0.0,
        initial_pot=500.0,
        today=today,
    )
    assert res["projected_pot_gbp"] == 500.0
