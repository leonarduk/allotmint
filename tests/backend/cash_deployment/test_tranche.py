"""Schedule dates and tranche order lists (#10480)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backend.cash_deployment import tranche as tranche_mod
from backend.cash_deployment.schedule import ScheduleInput, due_dates, tranche_amounts, window_end
from backend.cash_deployment.tranche import ORDER_LIST_LABEL, build_tranche, indicative_units, target_policy
from backend.common.allocation_policy import AllocationPolicy
from backend.common.rebalance_plan import bucket_holdings, split_classes, suggest_new_cash
from backend.common.sleeves import SleeveSetup


def _schedule(start: date, **overrides) -> ScheduleInput:
    fields = {"account": "isa", "total_amount_minor": 1_200_000, "tranches": 12, "start_date": start}
    return ScheduleInput(**{**fields, **overrides})


def test_twelve_monthly_tranches_have_twelve_due_dates(start):
    schedule = _schedule(start)
    dates = due_dates(schedule)
    assert len(dates) == 12
    assert dates[0] == start
    assert dates[1] == date(2026, 2, 15)
    assert dates[-1] == date(2026, 12, 15)
    assert window_end(schedule, 11) == date(2027, 1, 15)
    assert tranche_amounts(schedule) == [100_000] * 12


def test_month_end_start_clamps_without_drifting():
    dates = due_dates(_schedule(date(2026, 1, 31), tranches=4))
    assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_remainder_pence_go_on_the_last_tranche(start):
    amounts = tranche_amounts(_schedule(start, total_amount_minor=1_000_001, tranches=3))
    assert amounts == [333_333, 333_333, 333_335]
    assert sum(amounts) == 1_000_001


def test_weekly_and_quarterly_cadences(start):
    assert due_dates(_schedule(start, tranches=2, cadence="weekly"))[1] == date(2026, 1, 22)
    assert due_dates(_schedule(start, tranches=2, cadence="quarterly"))[1] == date(2026, 4, 15)


def test_split_is_identical_to_suggest_new_cash(portfolio, plan):
    policy = target_policy("plan", AllocationPolicy(), plan)
    result = build_tranche(portfolio, policy, SleeveSetup(), plan, "isa", 100_000, prices=lambda tickers: {})
    holdings = bucket_holdings(portfolio, split_classes(policy))
    assert result["split"] == suggest_new_cash(holdings, policy, 1000.0, "isa")
    assert result["label"] == ORDER_LIST_LABEL
    assert "per your plan" in result["label"]
    assert sum(o["amount_minor"] for o in result["orders"]) + result["keep_as_cash_minor"] == 100_000


def test_orders_use_only_the_plans_first_vehicle(portfolio, plan):
    policy = target_policy("plan", AllocationPolicy(), plan)
    result = build_tranche(
        portfolio, policy, SleeveSetup(), plan, "isa", 500_000, prices=lambda tickers: {"VWX.L": 12.5}
    )
    orders = {o["asset_class"]: o for o in result["orders"]}
    equity = orders["equity"]
    assert equity["ticker"] == "VWX.L"
    assert equity["price_gbp"] == 12.5
    assert equity["indicative_units"] == indicative_units(equity["amount_minor"] / 100, 12.5)
    # The plan names only a note for gilts: no instrument is invented, not even the held GLT.L.
    gilts = orders["long_gilts"]
    assert gilts["ticker"] is None
    assert gilts["vehicle_note"] == "a long gilt fund"
    assert gilts["indicative_units"] is None


def test_no_plan_means_no_vehicles(portfolio):
    policy = AllocationPolicy(targets={"equity": 90.0, "cash": 10.0})
    result = build_tranche(portfolio, policy, SleeveSetup(), None, "isa", 100_000, prices=lambda tickers: {})
    assert result["orders"] and all(o["ticker"] is None for o in result["orders"])


def test_plan_source_requires_a_plan():
    with pytest.raises(ValueError, match="no plan is saved"):
        target_policy("plan", AllocationPolicy(), None)
    with pytest.raises(ValueError, match="Set target allocations"):
        target_policy("policy", AllocationPolicy(), None)


def test_indicative_units_round_down_and_need_a_price():
    assert indicative_units(100.0, 3.0) == 33.3333
    assert indicative_units(100.0, None) is None
    assert indicative_units(100.0, 0.0) is None


def test_gbx_close_is_converted_to_pounds(monkeypatch, portfolio, plan):
    """A ``.L`` close stored in pence (GBX) gives units at the pound price."""
    from backend.common import holding_utils, instrument_api

    frame = pd.DataFrame({"Date": [pd.Timestamp("2026-01-14")], "Close": [1250.0]})
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda **kwargs: frame)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args: 1.0)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda ticker: {"currency": "GBX"})
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda full, cache: tuple(full.split(".")))

    policy = target_policy("plan", AllocationPolicy(), plan)
    result = build_tranche(portfolio, policy, SleeveSetup(), plan, "isa", 500_000, prices=tranche_mod.default_prices)
    equity = next(o for o in result["orders"] if o["asset_class"] == "equity")
    assert equity["price_gbp"] == 12.5
    assert equity["indicative_units"] == indicative_units(equity["amount_minor"] / 100, 12.5)
