import pytest

from backend.common.pension import state_pension_age


@pytest.mark.parametrize(
    "dob, expected",
    [
        ("1950-01-01", 66),
        ("1965-07-23", 67),
        ("1978-12-31", 68),
    ],
)
def test_state_pension_age_thresholds(dob, expected):
    assert state_pension_age(dob) == expected


@pytest.mark.parametrize("dob", [None, "", "not-a-date"])
def test_state_pension_age_invalid(dob):
    assert state_pension_age(dob) is None
