"""1W/1M/1Y price changes on a holding (#10746)."""

import datetime as dt

import pytest

from backend.common import holding_utils
from backend.utils.pricing_dates import PricingDateCalculator

# Friday 2026-10-09 is the reporting date for Monday 2026-10-12.
CALC = PricingDateCalculator(today=dt.date(2026, 10, 12))
PRICING_DATE = CALC.reporting_date


@pytest.fixture
def closes(monkeypatch):
    """Serve closes from a dict keyed by date; missing dates have no close."""
    table: dict[dt.date, float] = {}
    seen: list[dt.date] = []

    def fake_price(ticker, exchange, d, field="Close_gbp"):
        seen.append(d)
        return table.get(d), "test"

    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", fake_price)
    return table, seen


def test_reporting_date_is_previous_friday():
    assert PRICING_DATE == dt.date(2026, 10, 9)


def test_changes_use_window_start_closes(closes):
    table, seen = closes
    table[dt.date(2026, 10, 2)] = 9.0  # 7 days back
    table[dt.date(2026, 9, 9)] = 8.0  # 30 days back
    table[dt.date(2025, 10, 9)] = 5.0  # 365 days back (a Thursday)

    out = holding_utils._period_changes("VOD", "L", 10, 10.0, PRICING_DATE, None, CALC)

    assert out == {"change_1w_gbp": 10.0, "change_1m_gbp": 20.0, "change_1y_gbp": 50.0}
    assert seen == [dt.date(2026, 10, 2), dt.date(2026, 9, 9), dt.date(2025, 10, 9)]


def test_window_start_on_weekend_rolls_back_to_friday(closes):
    table, seen = closes
    calc = PricingDateCalculator(today=dt.date(2026, 10, 14))  # reporting Tue 13th
    pricing_date = calc.reporting_date
    holding_utils._period_changes("VOD", "L", 1, 10.0, pricing_date, None, calc)
    # 13 Oct - 30 days = Sun 13 Sep -> Fri 11 Sep.
    assert seen[1] == dt.date(2026, 9, 11)


def test_missing_history_is_none_not_zero(closes):
    table, _ = closes
    table[dt.date(2026, 10, 2)] = 9.0

    out = holding_utils._period_changes("NEW", "L", 10, 10.0, PRICING_DATE, None, CALC)

    assert out["change_1w_gbp"] == 10.0
    assert out["change_1m_gbp"] is None
    assert out["change_1y_gbp"] is None


def test_acquired_inside_window_measures_from_acquisition(closes):
    table, seen = closes
    acq = dt.date(2026, 9, 21)
    table[dt.date(2026, 10, 2)] = 9.0
    table[acq] = 7.0

    out = holding_utils._period_changes("VOD", "L", 10, 10.0, PRICING_DATE, acq, CALC)

    assert out["change_1w_gbp"] == 10.0  # bought before the 1W window
    assert out["change_1m_gbp"] == 30.0  # from the purchase, not 30 days back
    assert out["change_1y_gbp"] == 30.0
    assert seen == [dt.date(2026, 10, 2), acq, acq]


def test_bought_on_the_pricing_date_has_zero_change(closes):
    _, seen = closes
    out = holding_utils._period_changes("VOD", "L", 10, 10.0, PRICING_DATE, PRICING_DATE, CALC)
    assert out == dict.fromkeys(holding_utils.PERIOD_CHANGE_WINDOWS, 0.0)
    assert seen == []


def test_closed_position_reports_no_period_change():
    out = holding_utils.enrich_holding({"ticker": "VOD.L", "units": 0}, dt.date(2026, 10, 12), price_cache={})
    assert {k: out[k] for k in holding_utils.PERIOD_CHANGE_WINDOWS} == dict.fromkeys(
        holding_utils.PERIOD_CHANGE_WINDOWS
    )


@pytest.mark.parametrize("px, units", [(None, 10), (10.0, 0)])
def test_unpriced_or_empty_holding_has_no_change(closes, px, units):
    out = holding_utils._period_changes("VOD", "L", units, px, PRICING_DATE, None, CALC)
    assert out == dict.fromkeys(holding_utils.PERIOD_CHANGE_WINDOWS)
