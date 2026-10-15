"""Exchange-aware gap detection (#10961)."""

import pandas as pd

from backend.timeseries.quality import compute_quality, find_gaps


def _frame(dates):
    return pd.DataFrame({"Date": dates, "Close": [1.0] * len(dates)})


def test_platinum_jubilee_is_not_a_gap_on_london():
    # Wed 1 Jun 2022 then Mon 6 Jun: Thu 2 / Fri 3 Jun were bank holidays.
    assert find_gaps(_frame(["2022-06-01", "2022-06-06"]), exchange="L") == []


def test_diamond_jubilee_is_not_a_gap_on_london():
    # Fri 1 Jun 2012 then Wed 6 Jun: Mon 4 / Tue 5 Jun were bank holidays.
    assert find_gaps(_frame(["2012-06-01", "2012-06-06"]), exchange="L") == []


def test_moved_spring_holiday_is_a_trading_day_on_london():
    # Mon 30 May 2022 was a normal day (the holiday moved to 2 June), so
    # Fri 27 May -> Wed 1 Jun misses Mon 30 and Tue 31 May.
    gaps = find_gaps(_frame(["2022-05-27", "2022-06-01"]), exchange="L")
    assert gaps == [{"start": "2022-05-30", "end": "2022-05-31", "missing_business_days": 2}]


def test_hurricane_sandy_is_not_a_gap_on_us_exchange():
    # NYSE closed Mon 29 / Tue 30 Oct 2012.
    assert find_gaps(_frame(["2012-10-26", "2012-10-31"]), exchange="N") == []


def test_september_11_closure_is_not_a_gap_on_us_exchange():
    assert find_gaps(_frame(["2001-09-10", "2001-09-17"]), exchange="N") == []


def test_us_series_missing_uk_jubilee_days_is_a_gap():
    # The NYSE traded through the UK jubilee, so missing those days is real.
    gaps = find_gaps(_frame(["2022-06-01", "2022-06-06"]), exchange="N")
    assert gaps == [{"start": "2022-06-02", "end": "2022-06-03", "missing_business_days": 2}]


def test_real_multi_day_hole_still_reported_on_us_exchange():
    # Thanksgiving (Thu 26 Nov 2026) is skipped, the rest of the fortnight is not.
    gaps = find_gaps(_frame(["2026-11-20", "2026-12-04"]), exchange="N")
    assert gaps == [{"start": "2026-11-23", "end": "2026-12-03", "missing_business_days": 8}]


def test_gap_threshold_days_still_applies_with_exchange():
    frame = _frame(["2026-01-05", "2026-01-08"])  # Tue 6 / Wed 7 missing
    assert find_gaps(frame, gap_threshold_days=2, exchange="N") == []
    assert len(find_gaps(frame, gap_threshold_days=1, exchange="N")) == 1


def test_compute_quality_uses_series_exchange():
    frame = _frame(["2012-10-26", "2012-10-31"])
    assert compute_quality(frame, "AAPL", "N")["gap_count"] == 0
    assert compute_quality(frame, "VOD", "L")["gap_count"] == 1
