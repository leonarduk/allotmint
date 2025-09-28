import datetime as dt

from backend.utils.pricing_dates import PricingDateCalculator


def test_reporting_and_previous_dates_skip_weekend():
    calc = PricingDateCalculator(today=dt.date(2024, 1, 8))  # Monday
    assert calc.reporting_date == dt.date(2024, 1, 5)
    assert calc.previous_pricing_date == dt.date(2024, 1, 4)


def test_lookback_anchor_from_reporting_date():
    calc = PricingDateCalculator(today=dt.date(2024, 1, 10))
    # reporting date -> 2024-01-09 (Tuesday)
    assert calc.reporting_date == dt.date(2024, 1, 9)
    assert calc.lookback_anchor(7) == dt.date(2024, 1, 2)


def test_lookback_range_forward_end_handles_weekend():
    calc = PricingDateCalculator(today=dt.date(2024, 3, 3))  # Sunday
    start, end = calc.lookback_range(5, end=calc.today, forward_end=True)
    # Weekend end should roll forward to Monday 2024-03-04
    assert end == dt.date(2024, 3, 4)
    # Start backs off five calendar days and then normalises to a weekday
    assert start == dt.date(2024, 2, 28)
