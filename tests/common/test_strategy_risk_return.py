"""Strategy points on the "Returns vs Volatility" chart."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backend.common import ledger_performance, strategy_risk_return
from backend.common.strategies import Strategy
from backend.timeseries.total_return import PRICE_RETURN_BASIS, TOTAL_RETURN_BASIS

END = dt.date(2024, 12, 31)
AFTER = END - dt.timedelta(days=365)


def _daily(start: dt.date, growth: float) -> pd.Series:
    """Business-day closes from ``start`` to ``END`` growing by ``growth`` each day."""
    days = pd.bdate_range(start, END)
    return pd.Series([100.0 * (1 + growth) ** i for i in range(len(days))], index=days)


# Stand-in ticker -> (closes, basis). Anything absent has no prices.
SERIES = {
    "VWRL.L": (_daily(AFTER - dt.timedelta(days=5), 0.001), TOTAL_RETURN_BASIS),
    "PHAU.L": (_daily(AFTER - dt.timedelta(days=5), 0.0005), PRICE_RETURN_BASIS),
    # Long gilts start mid-window, so they cannot stand in.
    "GLTL.L": (_daily(AFTER + dt.timedelta(days=30), 0.0002), TOTAL_RETURN_BASIS),
}


@pytest.fixture(autouse=True)
def fake_closes(monkeypatch):
    requested: list[str] = []

    def fake(ticker, start, end):
        requested.append(ticker)
        closes, basis = SERIES.get(ticker, (pd.Series(dtype=float), PRICE_RETURN_BASIS))
        return closes[(closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))], basis

    monkeypatch.setattr(ledger_performance, "load_gbp_total_return_closes", fake)
    return requested


def _days_in_window() -> int:
    """Daily returns in ``(AFTER, END]``: the first is measured from the last close on or before AFTER."""
    return len(pd.bdate_range(AFTER + dt.timedelta(days=1), END))


def _compute(targets, cash_rate=0.0):
    strategy = Strategy(id="s", name="S", targets=targets, builtin=True)
    return strategy_risk_return.compute_strategy_risk_return(strategy, 365, cash_rate=cash_rate, pricing_date=END)


def test_single_sleeve_matches_its_stand_in():
    result = _compute({"equity": 100.0})
    days = _days_in_window()
    assert result["series"] == {"equity": "VWRL.L"}
    assert result["missing"] == []
    assert result["return_basis"] == TOTAL_RETURN_BASIS
    assert result["period_return"] == pytest.approx(1.001**days - 1)
    assert result["volatility"] == pytest.approx(0.0, abs=1e-9)


def test_daily_rebalanced_weighted_return_and_gold_is_total_return():
    result = _compute({"equity": 50.0, "gold": 50.0})
    assert result["series"] == {"equity": "VWRL.L", "gold": "PHAU.L"}
    # Physical gold pays no income, so its price return is its total return.
    assert result["return_basis"] == TOTAL_RETURN_BASIS
    days = _days_in_window()
    assert result["period_return"] == pytest.approx(1.00075**days - 1)


def test_cash_accrues_the_risk_free_rate_by_calendar_day():
    cash_only = _compute({"cash": 100.0}, cash_rate=0.05)
    # The window starts on a Sunday; its accrual to Monday still counts.
    assert cash_only["period_return"] == pytest.approx(1.05 ** ((END - AFTER).days / 365) - 1)
    assert cash_only["series"] == {}

    result = _compute({"equity": 50.0, "cash": 50.0}, cash_rate=0.05)
    flat = _compute({"equity": 50.0, "cash": 50.0}, cash_rate=0.0)
    assert result["period_return"] > flat["period_return"]
    assert "cash" not in result["series"]


def test_cash_returns_follow_calendar_gaps():
    index = pd.DatetimeIndex(["2024-01-05", "2024-01-08", "2024-01-09"])
    returns = strategy_risk_return._cash_returns(index, 0.05)
    assert returns.iloc[1] == pytest.approx(1.05 ** (3 / 365) - 1)
    assert returns.iloc[2] == pytest.approx(1.05 ** (1 / 365) - 1)


def test_sleeve_without_a_stand_in_covering_the_window_scores_nothing(fake_closes):
    result = _compute({"equity": 50.0, "long_gilts": 25.0, "property": 25.0})
    assert result["missing"] == ["long_gilts", "property"]
    assert result["period_return"] is None
    assert result["volatility"] is None
    assert result["return_basis"] is None
    assert "GLTL.L" in fake_closes


def test_falls_through_to_a_later_stand_in(monkeypatch):
    series = {k: v for k, v in SERIES.items() if k != "VWRL.L"}
    series["IWRD.L"] = SERIES["VWRL.L"]
    monkeypatch.setattr(
        ledger_performance,
        "load_gbp_total_return_closes",
        lambda ticker, start, end: series.get(ticker, (pd.Series(dtype=float), PRICE_RETURN_BASIS)),
    )
    assert _compute({"equity": 100.0})["series"] == {"equity": "IWRD.L"}


def test_market_holidays_count_the_move_on_the_next_close():
    days = pd.bdate_range("2024-01-01", "2024-01-05")
    uk = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=days)
    us = pd.Series([100.0, 110.0, 121.0], index=days[[0, 2, 4]])  # shut on two days
    returns = strategy_risk_return.strategy_daily_returns(
        {"equity": 50.0, "small_cap_value": 50.0}, {"equity": uk, "small_cap_value": us}, 0.0
    )
    assert len(returns) == 4
    assert returns.iloc[0] == pytest.approx(0.5 * 0.01)  # US shut: no move that day
    assert returns.iloc[1] == pytest.approx(0.5 * (102 / 101 - 1) + 0.5 * 0.10)  # its move lands on its next close


def test_staggered_stand_in_starts_do_not_touch_the_window():
    """A sleeve whose first close falls between another's and the window start only lacks pre-window returns."""
    days = pd.bdate_range("2024-01-01", "2024-01-10")
    early = pd.Series(range(100, 108), index=days[:8], dtype=float)
    late = pd.Series([50.0, 51.0, 52.0, 53.0, 54.0], index=days[3:8])
    returns = strategy_risk_return.strategy_daily_returns(
        {"equity": 50.0, "gold": 50.0}, {"equity": early, "gold": late}, 0.0
    )
    window = returns[returns.index > days[3]]  # window starts on the later sleeve's first close
    assert window.iloc[0] == pytest.approx(0.5 * (104 / 103 - 1) + 0.5 * (51 / 50 - 1))
    assert len(window) == 4


def test_stand_in_whose_prices_stop_before_the_window_end_is_skipped(monkeypatch):
    stale = SERIES["VWRL.L"][0]
    stale = stale[stale.index <= pd.Timestamp(END - dt.timedelta(days=30))]
    series = {"VWRL.L": (stale, TOTAL_RETURN_BASIS), "IWRD.L": SERIES["VWRL.L"]}
    monkeypatch.setattr(
        ledger_performance,
        "load_gbp_total_return_closes",
        lambda ticker, start, end: series.get(ticker, (pd.Series(dtype=float), PRICE_RETURN_BASIS)),
    )
    assert _compute({"equity": 100.0})["series"] == {"equity": "IWRD.L"}

    del series["IWRD.L"]
    assert _compute({"equity": 100.0})["missing"] == ["equity"]


def test_staggered_starts_that_cover_the_window_start_score_every_window_day():
    """Through the whole computation: a later first close, still before AFTER, loses no in-window return."""
    series = dict(SERIES)
    series["PHAU.L"] = (_daily(AFTER - dt.timedelta(days=2), 0.0005), PRICE_RETURN_BASIS)  # Friday, after VWRL.L starts
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            ledger_performance,
            "load_gbp_total_return_closes",
            lambda ticker, start, end: series.get(ticker, (pd.Series(dtype=float), PRICE_RETURN_BASIS)),
        )
        result = _compute({"equity": 50.0, "gold": 50.0})
    assert result["period_return"] == pytest.approx(1.00075 ** _days_in_window() - 1)
