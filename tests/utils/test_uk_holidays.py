from datetime import date

from backend.utils.uk_holidays import (
    is_uk_business_day,
    uk_bank_holidays,
    uk_business_days_between,
)


def test_uk_bank_holidays_2026_known_dates():
    holidays = uk_bank_holidays(2026)
    assert date(2026, 1, 1) in holidays  # New Year's Day
    assert date(2026, 4, 3) in holidays  # Good Friday
    assert date(2026, 4, 6) in holidays  # Easter Monday
    assert date(2026, 5, 4) in holidays  # Early May bank holiday
    assert date(2026, 5, 25) in holidays  # Spring bank holiday
    assert date(2026, 8, 31) in holidays  # Summer bank holiday
    assert date(2026, 12, 25) in holidays
    assert date(2026, 12, 28) in holidays  # Boxing Day substitute (26th is Sat)


def test_new_years_day_weekend_substitution():
    # 1 Jan 2028 is a Saturday -> substitute holiday is Monday 3 Jan 2028.
    holidays = uk_bank_holidays(2028)
    assert date(2028, 1, 3) in holidays
    assert date(2028, 1, 1) not in holidays


def test_is_uk_business_day_excludes_weekends_and_holidays():
    assert is_uk_business_day(date(2026, 1, 5)) is True  # Monday
    assert is_uk_business_day(date(2026, 1, 3)) is False  # Saturday
    assert is_uk_business_day(date(2026, 1, 4)) is False  # Sunday
    assert is_uk_business_day(date(2026, 1, 1)) is False  # New Year's Day


def test_uk_business_days_between_excludes_christmas_period():
    days = uk_business_days_between(date(2026, 12, 23), date(2026, 12, 29))
    # 23rd Wed, 24th Thu are business days; 25/26/27/28 are holiday/weekend; 29th Tue.
    assert days == [date(2026, 12, 23), date(2026, 12, 24), date(2026, 12, 29)]


def test_uk_business_days_between_empty_when_start_after_end():
    assert uk_business_days_between(date(2026, 1, 5), date(2026, 1, 1)) == []
