"""Historical drawdown simulation (#10484): hand-worked values, non-wrapping windows, missing years."""

from __future__ import annotations

import pytest

from backend.retirement.drawdown import (
    DrawdownInputs,
    historical_windows,
    income_at_survival,
    run_window,
    simulate,
    window_sustainable_income,
)
from backend.retirement.mapping import plan_real_returns


def test_zero_real_returns_spread_the_pot_evenly():
    # 30,000 over 3 years at 0% real: 10,000 a year exactly.
    assert window_sustainable_income(DrawdownInputs(30000, 3), [0.0, 0.0, 0.0]) == 10000.00


def test_constant_real_return_matches_annuity_due():
    # Withdraw at the start of each year, 5% real growth:
    # 10,000 = I * (1 + 1/1.05 + 1/1.05^2) = I * 2.859410  =>  I = 3,497.22
    assert window_sustainable_income(DrawdownInputs(10000, 3), [0.05, 0.05, 0.05]) == 3497.22


def test_state_pension_reduces_pot_withdrawals_from_its_start_year():
    # 1,000 pot, 2 years, 0% real, state pension 300 from year 1:
    # I + (I - 300) = 1,000  =>  I = 650.
    inputs = DrawdownInputs(1000, 2, state_pension=300, state_pension_from_year=1)
    assert window_sustainable_income(inputs, [0.0, 0.0]) == 650.00


def test_state_pension_above_income_is_not_added_to_pot():
    inputs = DrawdownInputs(100, 2, state_pension=500, state_pension_from_year=0)
    run = run_window(inputs, [0.0, 0.0], 400)
    assert run.survived and run.final_pot == 100


def test_run_window_fails_when_pot_cannot_pay():
    run = run_window(DrawdownInputs(1000, 2), [-0.5, 0.0], 600)
    # Year 0: 1000 - 600 = 400, halves to 200; year 1 needs 600.
    assert not run.survived and run.years_paid == 1


SMALL = {1: 0.10, 2: -0.10, 3: 0.0, 4: 0.20}


def test_hand_worked_windows_and_survival_levels():
    # Pot 1,000 over 2 years; a window starting in a year with real return r survives
    # (1000 - I)(1 + r) >= I, i.e. I = 1000 (1 + r) / (2 + r):
    #   start 1 (r=+10%): 1100/2.1 = 523.80 ; start 2 (r=-10%): 900/1.9 = 473.68 ; start 3 (r=0): 500.
    result = simulate(SMALL, DrawdownInputs(1000, 2), survival_levels=(100, 60))
    assert result["windows"]["start_years"] == [1, 2, 3]
    levels = {row["survival_pct"]: row["income_gbp"] for row in result["sustainable_income"]}
    assert levels == {100.0: 473.68, 60.0: 500.00}
    assert result["worst"] == {"start_year": 2, "end_year": 3, "sustainable_income_gbp": 473.68}
    assert result["median"] == {"start_year": 3, "end_year": 4, "sustainable_income_gbp": 500.00}
    assert result["best"] == {"start_year": 1, "end_year": 2, "sustainable_income_gbp": 523.80}


def test_window_running_past_last_year_is_dropped_not_wrapped():
    result = simulate(SMALL, DrawdownInputs(1000, 2), survival_levels=(100,))
    # Year 4 would need year 5; wrapping to year 1 would add a 4th window (r=+20%) - it must not.
    assert result["windows"]["count"] == 3
    assert result["windows"]["dropped_past_last_year"] == 1
    assert 4 not in result["windows"]["start_years"]


def test_missing_year_excludes_windows_instead_of_counting_as_zero():
    with_gap = {1: 0.10, 2: None, 3: 0.0, 4: 0.20}
    windows = historical_windows(with_gap, 2)
    assert windows.start_years == [3]
    assert windows.dropped_missing_data == [1, 2]
    as_zero = simulate({**with_gap, 2: 0.0}, DrawdownInputs(1000, 2), (100,))
    gap = simulate(with_gap, DrawdownInputs(1000, 2), (100,))
    assert gap["windows"]["count"] == 1 and as_zero["windows"]["count"] == 3


def test_no_complete_window_returns_empty_summary():
    result = simulate({1: 0.0}, DrawdownInputs(1000, 5), (100,))
    assert result["windows"]["count"] == 0
    assert result["sustainable_income"] == [] and result["worst"] is None


def test_floor_counts_windows_dipping_below():
    result = simulate(SMALL, DrawdownInputs(1000, 2), survival_levels=(100,), floor_gbp=500)
    floor = result["floor"]
    assert floor["at_income_gbp"] == 473.68
    # min_pot is the lowest end-of-year pot over the whole window. After year 1: start 1 has
    # (1000-473.68)*1.1 = 578.95, start 2 has 526.32*0.9 = 473.69, start 3 has 526.32; year 2 then
    # pays 473.68 out of each, leaving every window below 500 at some point.
    assert floor["windows_below_floor"] == 3
    assert floor["windows_total"] == 3


def test_income_at_survival_rules():
    incomes = [400.0, 500.0, 600.0, 700.0]
    assert income_at_survival(incomes, 100) == 400.0
    assert income_at_survival(incomes, 75) == 500.0
    assert income_at_survival(incomes, 50) == 600.0
    assert income_at_survival(incomes, 1) == 700.0
    # Non-divisor: 90% of 3 windows rounds up to all 3 (at least 90% must survive).
    assert income_at_survival([400.0, 500.0, 600.0], 90) == 400.0
    # 0.95 * 20 is 18.999... in floats; it must still need 19 windows, not 20.
    assert income_at_survival([float(i) for i in range(1, 21)], 95) == 2.0
    with pytest.raises(ValueError):
        income_at_survival(incomes, 0)
    with pytest.raises(ValueError):
        income_at_survival([], 90)


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        DrawdownInputs(1000, 0)
    with pytest.raises(ValueError):
        DrawdownInputs(-1, 5)
    with pytest.raises(ValueError):
        run_window(DrawdownInputs(1000, 2), [0.0], 10)
    with pytest.raises(ValueError):
        simulate(SMALL, DrawdownInputs(1000, 2), survival_levels=())


def test_thirty_year_fixture_cash_plan_matches_closed_form(synthetic_history):
    # Cash is +2% real every year in the fixture, so every 25-year window is the same annuity due:
    # I = 100,000 / sum_{t=0..24} 1.02^-t = 100,000 / 19.91393 = 5,021.61.
    returns = plan_real_returns({"cash": 100}, synthetic_history)
    result = simulate(returns.real_returns, DrawdownInputs(100000, 25), survival_levels=(100,))
    assert result["windows"]["start_years"] == [1990, 1991, 1992, 1993, 1994, 1995]
    assert result["windows"]["dropped_past_last_year"] == 24
    assert result["sustainable_income"] == [{"survival_pct": 100.0, "income_gbp": 5021.61}]


def test_thirty_year_fixture_excludes_windows_missing_gold(synthetic_history):
    returns = plan_real_returns({"cash": 50, "gold": 50}, synthetic_history)
    result = simulate(returns.real_returns, DrawdownInputs(100000, 25), survival_levels=(90, 100))
    assert result["windows"]["start_years"] == [1992, 1993, 1994, 1995]
    assert result["windows"]["dropped_missing_data"] == [1990, 1991]
    levels = [row["income_gbp"] for row in result["sustainable_income"]]
    assert levels[0] >= levels[1] > 0


def test_deterministic():
    a = simulate(SMALL, DrawdownInputs(1000, 2), (90, 100), floor_gbp=100)
    b = simulate(SMALL, DrawdownInputs(1000, 2), (90, 100), floor_gbp=100)
    assert a == b
