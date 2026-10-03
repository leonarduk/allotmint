"""Tests for scripts/repair_mixed_source_timeseries.py (#8597)."""

from __future__ import annotations

import pandas as pd

from scripts import repair_mixed_source_timeseries as repair


def _rows(dates: list[str], closes: list[float], source: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates).astype("datetime64[ms]"),
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [0.0] * len(dates),
            "Ticker": ["ADM.L" if source == "Yahoo" else "ADM"] * len(dates),
            "Source": [source] * len(dates),
        }
    )


def _mixed(path) -> None:
    """Yahoo ~1470p with Stooq ~1110p rows interleaved, as ADM_L was in 2015."""
    frame = pd.concat(
        [
            _rows(["2015-03-02", "2015-03-03", "2015-03-05"], [1469.89, 1456.94, 1507.73], "Yahoo"),
            _rows(["2015-03-04", "2015-03-06"], [1110.38, 1152.98], "Stooq"),
        ],
        ignore_index=True,
    ).sort_values("Date")
    frame.to_parquet(path, index=False)


def test_drops_minority_source_on_a_different_basis(tmp_path):
    path = tmp_path / "ADM_L.parquet"
    _mixed(path)

    report = repair.repair_file(path, refill=False)

    assert report.primary == "Yahoo"
    assert report.dropped == {"Stooq": 2}
    assert report.jumps_before == 3
    assert report.jumps_after == 0
    assert report.frame["Source"].unique().tolist() == ["Yahoo"]


def test_keeps_minority_source_on_the_same_basis(tmp_path):
    path = tmp_path / "ABC_L.parquet"
    pd.concat(
        [_rows(["2024-01-01", "2024-01-02"], [100.0, 101.0], "Yahoo"), _rows(["2024-01-03"], [101.5], "Stooq")]
    ).to_parquet(path, index=False)

    report = repair.repair_file(path, refill=False)

    assert report.dropped == {}
    assert report.kept_sources == ["Stooq"]
    assert len(report.frame) == 3


def test_single_source_file_is_skipped(tmp_path):
    path = tmp_path / "ABC_L.parquet"
    _rows(["2024-01-01"], [1.0], "Yahoo").to_parquet(path, index=False)

    assert repair.repair_file(path, refill=False) is None


def test_refill_uses_yahoo_only_when_it_matches_the_kept_basis(tmp_path, monkeypatch):
    path = tmp_path / "ADM_L.parquet"
    _mixed(path)
    calls = []

    def fake_fetch(symbol, exchange, start, end):
        calls.append((symbol, exchange))
        return _rows(
            ["2015-03-02", "2015-03-03", "2015-03-04", "2015-03-05", "2015-03-06"],
            [1465.41, 1452.51, 1448.53, 1503.14, 1504.13],
            "Yahoo",
        )

    import backend.timeseries.fetch_yahoo_timeseries as yahoo

    monkeypatch.setattr(yahoo, "fetch_yahoo_timeseries_range", fake_fetch)

    report = repair.repair_file(path, refill=True)

    assert calls == [("ADM", "L")]
    assert report.refilled == 2
    assert report.frame["Close"].tolist() == [1469.89, 1456.94, 1448.53, 1507.73, 1504.13]
    assert report.jumps_after == 0


def test_refill_rejected_when_yahoo_is_on_another_basis(tmp_path, monkeypatch):
    path = tmp_path / "ADM_L.parquet"
    _mixed(path)
    import backend.timeseries.fetch_yahoo_timeseries as yahoo

    monkeypatch.setattr(
        yahoo,
        "fetch_yahoo_timeseries_range",
        lambda *_a: _rows(["2015-03-02", "2015-03-04"], [1100.0, 1110.0], "Yahoo"),
    )

    report = repair.repair_file(path, refill=True)

    assert report.refilled == 0
    assert len(report.frame) == 3


def test_main_dry_run_leaves_file_untouched_and_apply_rewrites(tmp_path, capsys):
    path = tmp_path / "ADM_L.parquet"
    _mixed(path)

    repair.main([str(tmp_path)])
    assert len(pd.read_parquet(path)) == 5
    assert "ADM_L.parquet" in capsys.readouterr().out

    repair.main([str(tmp_path), "--ticker", "ADM_L", "--apply"])
    assert pd.read_parquet(path)["Source"].unique().tolist() == ["Yahoo"]
