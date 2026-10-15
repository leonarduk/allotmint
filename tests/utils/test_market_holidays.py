from datetime import date

from backend.utils.market_holidays import (
    business_days_between,
    exchange_holidays,
    nyse_holidays,
    tsx_holidays,
    xetra_holidays,
)
from backend.utils.uk_holidays import uk_bank_holidays


def test_nyse_holidays_2026():
    assert nyse_holidays(2026) == frozenset(
        {
            date(2026, 1, 1),
            date(2026, 1, 19),  # Martin Luther King Jr. Day
            date(2026, 2, 16),  # Washington's Birthday
            date(2026, 4, 3),  # Good Friday
            date(2026, 5, 25),  # Memorial Day
            date(2026, 6, 19),  # Juneteenth
            date(2026, 7, 3),  # Independence Day observed (4th is a Saturday)
            date(2026, 9, 7),  # Labor Day
            date(2026, 11, 26),  # Thanksgiving
            date(2026, 12, 25),
        }
    )


def test_nyse_holidays_special_closures():
    for closed in (
        date(2001, 9, 11),
        date(2001, 9, 14),
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2025, 1, 9),
    ):
        assert closed in nyse_holidays(closed.year), closed


def test_nyse_new_year_on_saturday_is_not_observed():
    # 1 Jan 2022 was a Saturday; the NYSE traded on Friday 31 Dec 2021.
    assert date(2021, 12, 31) not in nyse_holidays(2021)
    assert date(2021, 12, 31) not in nyse_holidays(2022)


def test_nyse_does_not_close_for_uk_jubilee():
    assert date(2022, 6, 2) not in nyse_holidays(2022)
    assert date(2022, 6, 3) not in nyse_holidays(2022)


def test_xetra_holidays_2026():
    holidays = xetra_holidays(2026)
    for closed in (
        date(2026, 4, 3),
        date(2026, 4, 6),
        date(2026, 5, 1),
        date(2026, 12, 24),
        date(2026, 12, 31),
    ):
        assert closed in holidays, closed


def test_tsx_holidays_2026():
    holidays = tsx_holidays(2026)
    for closed in (
        date(2026, 2, 16),  # Family Day
        date(2026, 5, 18),  # Victoria Day
        date(2026, 7, 1),  # Canada Day
        date(2026, 8, 3),  # Civic Holiday
        date(2026, 10, 12),  # Thanksgiving
        date(2026, 12, 28),  # Boxing Day substitute (26th is a Saturday)
    ):
        assert closed in holidays, closed


def test_exchange_holidays_picks_calendar_by_exchange():
    assert exchange_holidays("N", 2012) == nyse_holidays(2012)
    assert exchange_holidays("nasdaq", 2012) == nyse_holidays(2012)
    assert exchange_holidays("L", 2022) == uk_bank_holidays(2022)
    assert exchange_holidays("DE", 2022) == xetra_holidays(2022)
    assert exchange_holidays("TO", 2022) == tsx_holidays(2022)


def test_exchange_holidays_unknown_exchange_falls_back_to_uk():
    assert exchange_holidays("ZZ", 2022) == uk_bank_holidays(2022)
    assert exchange_holidays(None, 2022) == uk_bank_holidays(2022)


def test_business_days_between_uses_exchange_calendar():
    # Thanksgiving 2026 (Thu 26 Nov) is a US closure but a London trading day.
    us_days = business_days_between(date(2026, 11, 25), date(2026, 11, 27), "N")
    uk_days = business_days_between(date(2026, 11, 25), date(2026, 11, 27), "L")
    assert us_days == [date(2026, 11, 25), date(2026, 11, 27)]
    assert uk_days == [date(2026, 11, 25), date(2026, 11, 26), date(2026, 11, 27)]
    assert business_days_between(date(2026, 1, 5), date(2026, 1, 1), "N") == []
