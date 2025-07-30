import pytest
from backend.utils.period_utils import parse_period_to_days


@pytest.mark.parametrize(
    "period,expected_days",
    [
        ("1d", 1),
        ("5d", 5),
        ("2w", 14),
        ("3mo", 90),
        ("1y", 365),
        ("2y", 730),
        ("10y", 3650),
        ("12MO", 360),      # case-insensitive
        ("1Y", 365),
        ("  3mo  ", 90),    # spaces allowed
    ]
)
def test_valid_periods(period, expected_days):
    assert parse_period_to_days(period) == expected_days


@pytest.mark.parametrize("invalid_period", ["", "abc", "3", "mo3", "7M", "1year", "4 weeks"])
def test_invalid_periods(invalid_period):
    with pytest.raises(ValueError):
        parse_period_to_days(invalid_period)


def test_case_insensitivity_and_trim():
    assert parse_period_to_days(" 2W ") == 14
    assert parse_period_to_days("6MO") == 180
