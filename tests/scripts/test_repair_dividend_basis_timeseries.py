"""Tests for scripts/repair_dividend_basis_timeseries.py (#9340)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.timeseries.corporate_actions import DIVIDEND, load_dividends
from scripts import repair_dividend_basis_timeseries as repair

DAYS = pd.bdate_range("2026-01-05", periods=60)
RAW = pd.Series([50.0 + (i % 5) * 0.5 for i in range(len(DAYS))], index=DAYS)
# Stored rows came from three fetches adjusted at different times: 0.98 for
# the first 20 days, 0.99 for the next 25 (step mid-way between dividends, i.e.
# at an overlap edge), then raw.
STORED_RATIOS = [0.98] * 20 + [0.99] * 25 + [1.0] * 15
EX_DATES = [DAYS[45]]


def _meta(closes, dates, source="Yahoo") -> pd.DataFrame:
    closes = [round(c, 2) for c in closes]
    return pd.DataFrame(
        {
            "Date": pd.DatetimeIndex(dates).astype("datetime64[ms]"),
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": 100.0,
            "Ticker": "ABC.L",
            "Source": source,
        }
    )


def _fetcher(raw_dates=DAYS):
    def fetch(symbol, exchange, start, end):
        assert (symbol, exchange) == ("ABC", "L")
        prices = _meta(RAW[raw_dates].tolist(), raw_dates)
        actions = pd.DataFrame(
            {"Date": EX_DATES, "Action": DIVIDEND, "Value": 0.5, "Currency": "GBP", "Source": "Yahoo"}
        )
        return prices, actions

    return fetch


@pytest.fixture
def mixed_file(tmp_path):
    meta = tmp_path / "timeseries" / "meta"
    meta.mkdir(parents=True)
    path = meta / "ABC_L.parquet"
    _meta((RAW * STORED_RATIOS).tolist(), DAYS).to_parquet(path, index=False)
    return path


def test_dry_run_reports_basis_segments(mixed_file):
    report = repair.rebase_file(mixed_file, fetcher=_fetcher())

    assert [round(s.ratio, 2) for s in report.segments] == [0.98, 0.99, 1.0]
    assert [s.rows for s in report.segments] == [20, 25, 15]
    # 0.98 -> 0.99 has no dividend between: a fabricated overlap-edge step.
    # 0.99 -> 1.00 is at the ex-date.
    assert report.stray == 1
    assert report.max_dev == pytest.approx(0.02, abs=1e-3)
    assert report.changed == 45
    assert report.dividends == 1
    line = repair.format_report(report)
    assert "ABC_L.parquet" in line


def test_already_raw_file_has_one_segment_and_no_changes(tmp_path):
    path = tmp_path / "ABC_L.parquet"
    _meta(RAW.tolist(), DAYS).to_parquet(path, index=False)

    report = repair.rebase_file(path, fetcher=_fetcher())

    assert len(report.segments) == 1
    assert report.changed == 0
    assert report.max_dev == pytest.approx(0.0)


def test_rebased_frame_keeps_only_on_basis_rows_yahoo_lacks(tmp_path):
    path = tmp_path / "ABC_L.parquet"
    _meta((RAW * STORED_RATIOS).tolist(), DAYS).to_parquet(path, index=False)
    raw_dates = DAYS.delete([5, 55])  # Yahoo lacks one adjusted-era and one raw-era date

    report = repair.rebase_file(path, fetcher=_fetcher(raw_dates))

    assert report.dropped == 1
    frame = report.frame.set_index("Date")
    assert DAYS[5] not in frame.index
    assert DAYS[55] in frame.index
    assert frame.loc[DAYS[10], "Close"] == RAW[DAYS[10]]


def test_main_dry_run_writes_nothing(mixed_file, capsys, monkeypatch):
    before = mixed_file.read_bytes()
    monkeypatch.setattr(repair, "fetch_raw", _fetcher())

    assert repair.main([str(mixed_file.parent), "--ticker", "abc_l", "--segments"]) == 0

    assert mixed_file.read_bytes() == before
    assert "stored/raw=0.9800" in capsys.readouterr().out
    assert load_dividends("ABC", "L", base=str(mixed_file.parent.parent)).empty


def test_main_apply_rewrites_raw_rows_and_stores_dividends(mixed_file, monkeypatch):
    monkeypatch.setattr(repair, "fetch_raw", _fetcher())

    repair.main([str(mixed_file.parent), "--apply"])

    stored = pd.read_parquet(mixed_file).set_index("Date")["Close"]
    assert stored.tolist() == [round(c, 2) for c in RAW.tolist()]
    dividends = load_dividends("ABC", "L", base=str(mixed_file.parent.parent))
    assert dividends.to_dict() == {DAYS[45]: 0.5}
