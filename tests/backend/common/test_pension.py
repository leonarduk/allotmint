import datetime as dt

import pytest

from backend.common.pension import (
    DEFAULT_ANNUITY_MULTIPLE,
    _age_from_dob,
    estimate_db_pension_value,
    forecast_pension,
    state_pension_age,
    state_pension_age_uk,
)


@pytest.mark.parametrize(
    "dob, expected",
    [
        ("1954-10-05", 65),  # last day before the 66 threshold
        ("1954-10-06", 66),
        ("1960-04-05", 66),
        ("1960-04-06", 67),
        ("1977-04-05", 67),
        ("1977-04-06", 68),
        ("2050-01-01", 68),  # far future still uses final band
    ],
)
def test_state_pension_age_uk_boundaries(dob: str, expected: int) -> None:
    assert state_pension_age_uk(dob) == expected


def test_state_pension_age_uk_invalid_string() -> None:
    with pytest.raises(ValueError):
        state_pension_age_uk("not-a-date")


@pytest.mark.parametrize(
    "dob, expected",
    [
        ("1959-12-31", 66),
        ("1960-04-05", 66),
        ("1960-04-06", 67),
        ("1977-04-05", 67),
        ("1977-04-06", 68),
        ("2050-01-01", 68),
    ],
)
def test_state_pension_age_valid_inputs(dob: str, expected: int) -> None:
    assert state_pension_age(dob) == expected


def test_state_pension_age_invalid_inputs() -> None:
    assert state_pension_age("invalid") is None
    assert state_pension_age(None) is None


@pytest.mark.parametrize(
    "dob, today",
    [
        ("2000-01-01", dt.date(2024, 1, 1)),
        ("1980-06-15", dt.date(2020, 6, 15)),
    ],
)
def test_age_from_dob_fractional_years(dob: str, today: dt.date) -> None:
    expected = (today - dt.date.fromisoformat(dob)).days / 365.25
    assert _age_from_dob(dob, today) == pytest.approx(expected)


def test_age_from_dob_invalid_and_future_dates() -> None:
    future_today = dt.date(2020, 1, 1)
    assert _age_from_dob("", future_today) is None
    assert _age_from_dob("not-a-date", future_today) is None
    # future birthdays return negative ages instead of failing
    negative_age = _age_from_dob("2050-01-01", future_today)
    assert negative_age is not None and negative_age < 0


def test_estimate_db_pension_value_with_growth_and_custom_multiple() -> None:
    result = estimate_db_pension_value(
        annual_income_gbp=5000,
        normal_retirement_age=65,
        current_age=45,
        assumed_cpi_pct=3.0,
        annuity_multiple=25,
        today=dt.date(2024, 1, 1),
    )

    expected_years = 20.0
    expected_growth = (1 + 0.03) ** expected_years
    expected_income = 5000 * expected_growth
    assert result["years_to_start"] == pytest.approx(expected_years)
    assert result["income_at_start_gbp"] == pytest.approx(expected_income)
    assert result["annuity_multiple_used"] == 25
    assert result["est_capital_value_gbp"] == pytest.approx(expected_income * 25)
    assert result["annual_income_now_gbp"] == pytest.approx(5000)


def test_estimate_db_pension_value_immediate_start() -> None:
    result = estimate_db_pension_value(
        annual_income_gbp=4000,
        normal_retirement_age=60,
        current_age=65,
        today=dt.date(2024, 1, 1),
    )

    assert result["years_to_start"] == pytest.approx(0.0)
    assert result["income_at_start_gbp"] == pytest.approx(4000)
    assert result["annuity_multiple_used"] == DEFAULT_ANNUITY_MULTIPLE
    assert result["est_capital_value_gbp"] == pytest.approx(4000 * DEFAULT_ANNUITY_MULTIPLE)


def test_forecast_pension_scenario() -> None:
    today = dt.date(2020, 1, 2)
    result = forecast_pension(
        dob="1990-01-01",
        retirement_age=32,
        death_age=35,
        db_pensions=[
            {"annual_income_gbp": 5000, "normal_retirement_age": 31},
            {"annual_income_gbp": 2000, "normal_retirement_age": 33},
        ],
        state_pension_annual=9000,
        contribution_annual=2000,
        investment_growth_pct=4.0,
        desired_income_annual=800,
        annuity_multiple=20,
        initial_pot=10000,
        today=today,
    )

    ages = [entry["age"] for entry in result["forecast"]]
    incomes = [entry["income"] for entry in result["forecast"]]
    assert ages == [30, 31, 32, 33, 34]
    assert incomes == [0.0, 5000.0, 14000.0, 16000.0, 16000.0]
    assert result["projected_pot_gbp"] == pytest.approx(15059.2)
    assert result["earliest_retirement_age"] == 34
    assert result["retirement_income_breakdown"]["state_pension_annual"] == pytest.approx(
        9000
    )
    assert result["retirement_income_breakdown"]["defined_benefit_annual"] == pytest.approx(
        5000
    )
    assert result["retirement_income_breakdown"]["defined_contribution_annual"] == pytest.approx(
        752.96,
        rel=1e-4,
    )
    assert result["retirement_income_total_annual"] == pytest.approx(14752.96, rel=1e-4)
    assert result["state_pension_annual"] == pytest.approx(9000)
    assert result["contribution_annual"] == pytest.approx(2000)
    assert result["desired_income_annual"] == pytest.approx(800)
    assert result["annuity_multiple_used"] == pytest.approx(20)
