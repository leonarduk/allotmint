"""Historical sequence-of-returns drawdown simulation (pure, deterministic).

Everything is in real terms (today's money). For a window of ``N`` consecutive
historical years starting in year ``y`` the simulation, each year ``t``:

1. takes this year's income need from the pot at the start of the year:
   ``income - state_pension`` once ``t >= state_pension_from_year`` (never
   below zero; a state pension above the income is not added to the pot);
2. fails the window if the pot cannot pay that in full;
3. grows the rest by year ``y + t``'s real return of the plan mix, which is
   rebalanced to the plan weights every year (see
   :func:`backend.retirement.mapping.plan_real_returns`).

A window survives when all ``N`` years are paid. Windows never wrap: one that
would run past the last data year is dropped, as is any window containing a
year with missing data (``None``), which is never treated as a 0% return.

A window's *sustainable income* is the highest constant real income it
survives, found by binary search (survival is monotone in the income). The
income sustainable at survival level ``p`` is then the highest income that at
least ``p``% of windows survive.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

#: Slack when comparing the pot with a withdrawal, so float noise never fails an exactly-funded year.
_EPSILON = 1e-6
_BISECTION_STEPS = 100


@dataclass(frozen=True)
class DrawdownInputs:
    start_pot: float
    years: int
    state_pension: float = 0.0
    state_pension_from_year: int = 0

    def __post_init__(self) -> None:
        if self.years < 1:
            raise ValueError("years must be at least 1")
        if self.start_pot < 0 or self.state_pension < 0:
            raise ValueError("start_pot and state_pension must not be negative")
        if self.state_pension_from_year < 0:
            raise ValueError("state_pension_from_year must not be negative")


@dataclass(frozen=True)
class WindowRun:
    survived: bool
    years_paid: int
    final_pot: float
    min_pot: float


def pot_need(inputs: DrawdownInputs, income: float, t: int) -> float:
    """What the pot pays in year ``t`` for a total real ``income``."""
    pension = inputs.state_pension if t >= inputs.state_pension_from_year else 0.0
    return max(income - pension, 0.0)


def run_window(inputs: DrawdownInputs, returns: Sequence[float], income: float) -> WindowRun:
    """Replay one window of real returns (``len(returns) == inputs.years``)."""
    if len(returns) != inputs.years:
        raise ValueError(f"window has {len(returns)} returns, expected {inputs.years}")
    pot = inputs.start_pot
    min_pot = pot
    for t, real_return in enumerate(returns):
        need = pot_need(inputs, income, t)
        if pot + _EPSILON < need:
            return WindowRun(survived=False, years_paid=t, final_pot=0.0, min_pot=0.0)
        pot = max(pot - need, 0.0) * (1.0 + real_return)
        min_pot = min(min_pot, pot)
    return WindowRun(survived=True, years_paid=inputs.years, final_pot=pot, min_pot=min_pot)


def window_sustainable_income(inputs: DrawdownInputs, returns: Sequence[float]) -> float:
    """Highest constant real income the window survives, rounded down to the penny."""
    low = 0.0
    # Year 0 alone needs more than the whole pot at this income, so it always fails.
    high = inputs.start_pot + inputs.state_pension + 1.0
    for _ in range(_BISECTION_STEPS):
        mid = (low + high) / 2.0
        if run_window(inputs, returns, mid).survived:
            low = mid
        else:
            high = mid
    return math.floor(low * 100.0 + 1e-6) / 100.0


@dataclass(frozen=True)
class Windows:
    start_years: list[int]
    dropped_past_last_year: list[int]
    dropped_missing_data: list[int]


def historical_windows(real_returns: Mapping[int, Optional[float]], years: int) -> Windows:
    """Start years of every complete, non-wrapping ``years``-long window."""
    if not real_returns:
        return Windows([], [], [])
    first, last = min(real_returns), max(real_returns)
    starts: list[int] = []
    past_end: list[int] = []
    missing: list[int] = []
    for start in range(first, last + 1):
        end = start + years - 1
        if end > last:
            past_end.append(start)
        elif any(real_returns.get(y) is None for y in range(start, end + 1)):
            missing.append(start)
        else:
            starts.append(start)
    return Windows(starts, past_end, missing)


def income_at_survival(incomes: Sequence[float], survival_pct: float) -> float:
    """Highest income that at least ``survival_pct``% of windows (with these sustainable incomes) survive."""
    if not incomes:
        raise ValueError("no windows")
    if not 0 < survival_pct <= 100:
        raise ValueError("survival_pct must be in (0, 100]")
    needed = max(1, math.ceil(round(survival_pct / 100.0 * len(incomes), 9)))
    return sorted(incomes, reverse=True)[needed - 1]


def _window_row(start: int, years: int, income: float) -> dict:
    return {"start_year": start, "end_year": start + years - 1, "sustainable_income_gbp": income}


def _floor_stats(
    inputs: DrawdownInputs, series: dict[int, list[float]], income: float, floor_gbp: Optional[float]
) -> Optional[dict]:
    if floor_gbp is None:
        return None
    below = [start for start, returns in series.items() if run_window(inputs, returns, income).min_pot < floor_gbp]
    return {
        "floor_gbp": floor_gbp,
        "at_income_gbp": income,
        "windows_below_floor": len(below),
        "windows_total": len(series),
        "pct_below_floor": round(100.0 * len(below) / len(series), 2),
        "start_years_below_floor": below,
    }


def simulate(
    real_returns: Mapping[int, Optional[float]],
    inputs: DrawdownInputs,
    survival_levels: Sequence[float] = (90.0, 95.0, 100.0),
    floor_gbp: Optional[float] = None,
) -> dict:
    """Replay every historical window and summarise sustainable incomes.

    The floor check uses the income at the first of ``survival_levels``.
    """
    if not survival_levels:
        raise ValueError("survival_levels must not be empty")
    windows = historical_windows(real_returns, inputs.years)
    summary = {
        "horizon_years": inputs.years,
        "start_pot_gbp": round(inputs.start_pot, 2),
        "state_pension_annual_gbp": round(inputs.state_pension, 2),
        "state_pension_from_year": inputs.state_pension_from_year,
        "windows": {
            "count": len(windows.start_years),
            "start_years": windows.start_years,
            "dropped_past_last_year": len(windows.dropped_past_last_year),
            "dropped_missing_data": windows.dropped_missing_data,
        },
    }
    if not windows.start_years:
        return {**summary, "sustainable_income": [], "worst": None, "median": None, "best": None, "floor": None}
    series = {s: [float(real_returns[y]) for y in range(s, s + inputs.years)] for s in windows.start_years}  # type: ignore[arg-type]
    per_window = {start: window_sustainable_income(inputs, returns) for start, returns in series.items()}
    incomes = list(per_window.values())
    levels = [{"survival_pct": float(p), "income_gbp": income_at_survival(incomes, p)} for p in survival_levels]
    ranked = sorted(per_window.items(), key=lambda item: (item[1], item[0]))
    worst, median, best = ranked[0], ranked[(len(ranked) - 1) // 2], ranked[-1]
    return {
        **summary,
        "sustainable_income": levels,
        "worst": _window_row(worst[0], inputs.years, worst[1]),
        "median": _window_row(median[0], inputs.years, median[1]),
        "best": _window_row(best[0], inputs.years, best[1]),
        "floor": _floor_stats(inputs, series, levels[0]["income_gbp"], floor_gbp),
    }
