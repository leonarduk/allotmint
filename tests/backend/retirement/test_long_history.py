"""Long-history CSV loader (#10484): blanks stay missing, resolution follows the timeseries cache base."""

from __future__ import annotations

import io

import pytest

from backend.retirement import long_history as lh
from tests.backend.retirement.conftest import FIXTURE

CSV = (
    "year,uk_cpi_inflation,gbp_per_usd,uk_cash,uk_govt_bond_10y,uk_equity,us_equity_gbp,"
    "ex_us_dev_equity_gbp,us_small_value_gbp,gold_gbp\n"
    "2000,0.02,0.5,0.04,0.03,0.10,,0.08,,\n"
    "2001,0.03,0.5,0.05,0.00,-0.20,0.05,0.07,0.0,0.01\n"
)


def test_blank_cells_are_missing_not_zero():
    history = lh.parse_long_history(CSV)
    assert history.years == (2000, 2001)
    assert history.value("us_equity_gbp", 2000) is None
    assert history.value("gold_gbp", 2000) is None
    # A genuine 0.0 return stays 0.0 and is distinct from a blank.
    assert history.value("us_small_value_gbp", 2001) == 0.0
    assert history.value("uk_govt_bond_10y", 2001) == 0.0
    assert history.cpi == {2000: 0.02, 2001: 0.03}


def test_coverage_reports_first_and_last_year_with_data():
    history = lh.parse_long_history(CSV)
    assert history.coverage("us_equity_gbp") == (2001, 2001)
    assert history.coverage("uk_cash") == (2000, 2001)
    assert history.coverage(lh.CPI_COLUMN) == (2000, 2001)


def test_gap_in_years_is_rejected():
    with pytest.raises(ValueError, match="consecutive"):
        lh.parse_long_history(CSV.replace("2001,", "2003,"))


def test_missing_required_columns_rejected():
    with pytest.raises(ValueError, match="year"):
        lh.parse_long_history("year,uk_cash\n2000,0.01\n")


def test_missing_block_column_is_noted():
    history = lh.parse_long_history("year,uk_cpi_inflation,uk_cash\n2000,0.02,0.04\n")
    assert history.blocks == {"uk_cash": {2000: 0.04}}
    assert "gold_gbp" in history.notes[0]


def test_load_local_fixture(synthetic_history):
    assert synthetic_history.years[0] == 1990 and synthetic_history.years[-1] == 2019
    assert synthetic_history.source == str(FIXTURE)
    assert synthetic_history.basis == "total_return"
    assert synthetic_history.coverage("us_small_value_gbp") == (1995, 2019)


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(lh.LongHistoryError, match="not found"):
        lh.load_long_history(str(tmp_path / "absent.csv"))


def test_malformed_file_raises_long_history_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("year,uk_cpi_inflation\n2000,abc\n", encoding="utf-8")
    with pytest.raises(lh.LongHistoryError, match="malformed"):
        lh.load_long_history(str(path))


def test_location_follows_timeseries_cache_base(monkeypatch):
    from backend.timeseries import cache

    monkeypatch.setattr(cache, "_CACHE_BASE", "s3://bucket/timeseries")
    assert lh.long_history_location() == "s3://bucket/timeseries/long_history/annual_returns_gbp.csv"


def test_reads_from_s3(monkeypatch):
    calls = {}

    class _Client:
        def get_object(self, Bucket, Key):
            calls["args"] = (Bucket, Key)
            return {"Body": io.BytesIO(CSV.encode("utf-8"))}

    import boto3

    monkeypatch.setattr(boto3, "client", lambda service, **_: _Client())
    history = lh.load_long_history("s3://bucket/timeseries/long_history/annual_returns_gbp.csv")
    assert calls["args"] == ("bucket", "timeseries/long_history/annual_returns_gbp.csv")
    assert history.years == (2000, 2001)


def test_s3_failure_is_long_history_error(monkeypatch):
    from botocore.exceptions import ClientError

    class _Client:
        def get_object(self, Bucket, Key):
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    import boto3

    monkeypatch.setattr(boto3, "client", lambda service, **_: _Client())
    with pytest.raises(lh.LongHistoryError, match="S3"):
        lh.load_long_history("s3://bucket/key.csv")


def test_default_location_used_when_none_given(monkeypatch):
    monkeypatch.setattr(lh, "long_history_location", lambda: str(FIXTURE))
    assert lh.load_long_history().source == str(FIXTURE)
