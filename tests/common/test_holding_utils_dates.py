import datetime as dt

from backend.common import holding_utils


def test_parse_date_accepts_datetime():
    d = dt.datetime(2024, 5, 6, 12, 0, 0)
    assert holding_utils._parse_date(d) == dt.date(2024, 5, 6)


def test_parse_date_accepts_date():
    d = dt.date(2024, 5, 6)
    assert holding_utils._parse_date(d) == d


def test_parse_date_accepts_iso_string():
    assert holding_utils._parse_date("2024-05-06") == dt.date(2024, 5, 6)


def test_parse_date_rejects_invalid():
    assert holding_utils._parse_date("not-a-date") is None
    assert holding_utils._parse_date(12345) is None


def test_nearest_weekday_forward_weekend():
    saturday = dt.date(2024, 1, 6)
    sunday = dt.date(2024, 1, 7)
    expected = dt.date(2024, 1, 8)
    assert holding_utils._nearest_weekday(saturday, True) == expected
    assert holding_utils._nearest_weekday(sunday, True) == expected


def test_nearest_weekday_backward_weekend():
    saturday = dt.date(2024, 1, 6)
    sunday = dt.date(2024, 1, 7)
    expected = dt.date(2024, 1, 5)
    assert holding_utils._nearest_weekday(saturday, False) == expected
    assert holding_utils._nearest_weekday(sunday, False) == expected
