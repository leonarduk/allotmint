import datetime as dt

from backend.common.pension import _age_from_dob


def test_age_from_dob_invalid():
    assert _age_from_dob("not-a-date", dt.date(2024, 1, 1)) is None
