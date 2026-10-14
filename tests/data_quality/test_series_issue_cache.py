"""Per-series result cache in ``aggregate_series_issues`` (#10754).

Each series' issues are reused while the files they are derived from are
unchanged, so a repeat visit to the Data Quality page does not re-check every
cached series. These tests pin when the cache is reused and when it is not.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from backend.config import config
from backend.data_quality import issues as issues_module
from backend.data_quality.issues import MAX_PREVIEW_OUTLIERS, IssueType, aggregate_series_issues


def _series_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=40)
    closes = [100.0 + i for i in range(len(dates))]
    closes[30] = 500.0  # one clear outlier
    return pd.DataFrame({"Date": dates, "Close": closes, "Ticker": ["WRONG"] * len(dates)})


def _touch(path: Path, *, bump_ns: int = 10**9) -> None:
    """Rewrite ``path`` and move its mtime forward, so its signature changes."""
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + bump_ns))


@pytest.fixture
def series_files(tmp_path, monkeypatch):
    """One cached series ABC.L whose input files live under ``tmp_path``.

    Returns the input files keyed by role plus a list recording each series load.
    """
    files = {
        "series": tmp_path / "ABC_L.parquet",
        "actions": tmp_path / "ABC_L.actions",
        "meta": tmp_path / "ABC.json",
        "overrides": tmp_path / "scaling_overrides.json",
    }
    for path in files.values():
        path.write_text("x", encoding="utf-8")
    loads: list[tuple[str, str]] = []

    def fake_load(ticker: str, exchange: str) -> pd.DataFrame:
        loads.append((ticker, exchange))
        return _series_frame()

    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.delenv("METADATA_BUCKET", raising=False)
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: [])
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", fake_load)
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})
    monkeypatch.setattr(issues_module, "meta_timeseries_cache_path", lambda t, e: str(files["series"]))
    monkeypatch.setattr(issues_module, "corporate_actions_path", lambda t, e: str(files["actions"]))
    monkeypatch.setattr(issues_module, "instrument_meta_path", lambda t, e: files["meta"])
    monkeypatch.setattr(issues_module, "scaling_override_paths", lambda: [files["overrides"]])
    return files, loads


def _as_dicts(issues):
    return [i.to_dict() for i in issues]


def test_repeat_call_reuses_cached_series_issues(series_files):
    _, loads = series_files

    first = aggregate_series_issues()
    second = aggregate_series_issues()

    assert loads == [("ABC", "L")]
    assert _as_dicts(second) == _as_dicts(first)
    assert {i.type for i in first} >= {IssueType.OUTLIERS, IssueType.TICKER_MISMATCH}


def test_cached_issues_are_independent_copies(series_files):
    first = aggregate_series_issues()
    first[0].preview["before"]["tampered"] = True
    first[0].entity["ticker"] = "ZZZ"

    second = aggregate_series_issues()

    assert "tampered" not in second[0].preview["before"]
    assert second[0].entity["ticker"] == "ABC"


@pytest.mark.parametrize("role", ["series", "actions", "meta", "overrides"])
def test_changed_input_file_rechecks_the_series(series_files, role):
    files, loads = series_files
    aggregate_series_issues()

    _touch(files[role])
    aggregate_series_issues()

    assert loads == [("ABC", "L"), ("ABC", "L")]


def test_different_options_recheck_the_series(series_files):
    _, loads = series_files
    aggregate_series_issues(outlier_sigma=3.0)
    aggregate_series_issues(outlier_sigma=4.0)
    assert len(loads) == 2


def test_tracked_status_change_rechecks_the_series(series_files, monkeypatch):
    _, loads = series_files
    aggregate_series_issues()
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: ["ABC.L"])
    aggregate_series_issues()
    assert len(loads) == 2


def test_new_day_rechecks_the_series(series_files, monkeypatch):
    """Staleness depends on today's date, so a cached result does not outlive the day."""
    _, loads = series_files
    aggregate_series_issues()

    class _Tomorrow(issues_module.date):
        @classmethod
        def today(cls):
            return issues_module.date(2099, 1, 1)

    monkeypatch.setattr(issues_module, "date", _Tomorrow)
    aggregate_series_issues()
    assert len(loads) == 2


def test_missing_local_parquet_is_never_cached(series_files):
    files, loads = series_files
    files["series"].unlink()
    aggregate_series_issues()
    aggregate_series_issues()
    assert len(loads) == 2


def test_aws_is_never_cached(series_files, monkeypatch):
    _, loads = series_files
    monkeypatch.setattr(config, "app_env", "aws")
    aggregate_series_issues()
    aggregate_series_issues()
    assert len(loads) == 2


def test_s3_metadata_is_never_cached(series_files, monkeypatch):
    _, loads = series_files
    monkeypatch.setenv("METADATA_BUCKET", "bucket")
    aggregate_series_issues()
    aggregate_series_issues()
    assert len(loads) == 2


def test_series_no_longer_cached_is_dropped(series_files, monkeypatch):
    aggregate_series_issues()
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [])

    assert aggregate_series_issues() == []
    assert issues_module._SERIES_ISSUE_CACHE == {}


def test_outlier_preview_lists_only_recent_points(monkeypatch):
    """The preview keeps the latest points and the full count; the description keeps the count too."""
    dates = pd.bdate_range("2025-01-06", periods=600)
    closes = [100.0] * len(dates)
    spikes = list(range(30, 600, 20))
    for pos in spikes:
        closes[pos] = 100.0 + 50.0 * (pos % 3 + 1)
    df = pd.DataFrame({"Date": dates, "Close": closes})
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: [])
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})

    outliers = next(i for i in aggregate_series_issues() if i.type == IssueType.OUTLIERS)

    before = outliers.preview["before"]
    assert before["outlier_count"] > MAX_PREVIEW_OUTLIERS
    assert len(before["outliers"]) == MAX_PREVIEW_OUTLIERS
    assert before["outliers"][-1]["date"] == dates[spikes[-1]].date().isoformat()
    assert outliers.description.startswith(f"{before['outlier_count']} outlier point(s)")
