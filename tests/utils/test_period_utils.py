import pytest

import pytest

from backend.utils.period_utils import parse_period_to_days


@pytest.mark.parametrize(
    "period,days",
    [
        ("1d", 1),
        ("2w", 14),
        ("3mo", 90),
        ("1y", 365),
        ("2W", 14),
    ],
)
def test_parse_period_to_days(period, days):
    """Valid period strings convert to expected day counts."""
    assert parse_period_to_days(period) == days


@pytest.mark.parametrize("period", ["", "5x", "abc"])
def test_parse_period_invalid_format(period):
    """Invalid period strings raise ValueError."""
    with pytest.raises(ValueError):
        parse_period_to_days(period)


def test_parse_period_unsupported_unit():
    """Unknown time units raise ValueError."""
    with pytest.raises(ValueError):
        parse_period_to_days("1q")
