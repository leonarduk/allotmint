import pandas as pd

from backend.timeseries.quality import (
    compute_quality,
    find_duplicate_dates,
    find_gaps,
    find_outliers,
)


def _df(rows):
    return pd.DataFrame(rows)


def test_compute_quality_empty_dataframe():
    result = compute_quality(pd.DataFrame(), "ABC", "L")
    assert result == {
        "ticker": "ABC",
        "exchange": "L",
        "total_points": 0,
        "first_date": None,
        "last_date": None,
        "gap_count": 0,
        "gaps": [],
        "duplicate_dates": [],
        "outliers": [],
    }


def test_find_duplicate_dates():
    df = _df(
        [
            {"Date": "2026-01-05", "Close": 1.0},
            {"Date": "2026-01-06", "Close": 1.0},
            {"Date": "2026-01-06", "Close": 1.1},
            {"Date": "2026-01-07", "Close": 1.0},
        ]
    )
    dupes = find_duplicate_dates(df)
    assert [d.isoformat() for d in dupes] == ["2026-01-06"]


def test_find_gaps_ignores_weekend():
    # Friday 2026-01-02 then Monday 2026-01-05 -- weekend only, no gap.
    df = _df([{"Date": "2026-01-02", "Close": 1.0}, {"Date": "2026-01-05", "Close": 1.0}])
    assert find_gaps(df) == []


def test_find_gaps_flags_missing_business_days():
    # Present: Mon 5th and the following Mon 12th; Tue-Fri (6th-9th) are
    # missing business days -- a 4-day gap, above the default threshold of 1.
    df = _df([{"Date": "2026-01-05", "Close": 1.0}, {"Date": "2026-01-12", "Close": 1.0}])
    gaps = find_gaps(df)
    assert len(gaps) == 1
    assert gaps[0] == {
        "start": "2026-01-06",
        "end": "2026-01-09",
        "missing_business_days": 4,
    }


def test_find_gaps_below_threshold_not_reported():
    # Single missing business day (Tue 6th) with threshold=1 is not a gap.
    df = _df([{"Date": "2026-01-05", "Close": 1.0}, {"Date": "2026-01-07", "Close": 1.0}])
    assert find_gaps(df, gap_threshold_days=1) == []
    assert len(find_gaps(df, gap_threshold_days=0)) == 1


def test_find_outliers_flags_spike():
    rows = [{"Date": f"2026-01-{d:02d}", "Close": 100.0} for d in range(1, 21)]
    rows.append({"Date": "2026-01-21", "Close": 1000.0})
    df = _df(rows)
    outliers = find_outliers(df, sigma=3.0, window=20)
    assert len(outliers) == 1
    assert outliers[0]["date"] == "2026-01-21"
    assert outliers[0]["value"] == 1000.0


def test_find_outliers_stable_series_has_none():
    rows = [{"Date": f"2026-01-{d:02d}", "Close": 100.0 + (d % 2) * 0.1} for d in range(1, 21)]
    df = _df(rows)
    assert find_outliers(df) == []


def test_compute_quality_aggregates_all_metrics():
    rows = [{"Date": f"2026-01-{d:02d}", "Close": 100.0} for d in range(5, 13) if d not in (6, 7, 8, 9)]
    df = _df(rows)
    result = compute_quality(df, "XYZ", "L", gap_threshold_days=1)
    assert result["ticker"] == "XYZ"
    assert result["exchange"] == "L"
    assert result["total_points"] == len(rows)
    assert result["first_date"] == "2026-01-05"
    assert result["last_date"] == "2026-01-12"
    assert result["gap_count"] == 1
    assert result["duplicate_dates"] == []
