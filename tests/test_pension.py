import datetime as dt

import pytest

from backend.common.pension import _age_from_dob, state_pension_age_uk


def test_age_from_dob_invalid():
    assert _age_from_dob("not-a-date", dt.date(2024, 1, 1)) is None


@pytest.mark.parametrize(
    "dob, expected",
    [
        ("1950-01-01", 65),
        ("1955-06-01", 66),
        ("1965-07-15", 67),
        ("1980-12-30", 68),
    ],
)
def test_state_pension_age_uk(dob, expected):
    assert state_pension_age_uk(dob) == expected


def test_state_pension_age_uk_invalid():
    with pytest.raises(ValueError):
        state_pension_age_uk("not-a-date")
