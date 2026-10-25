"""Tests for scripts/check_snapshot_scaling.py (#10352)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.utils import timeseries_helpers as th
from scripts import check_snapshot_scaling as check


@pytest.fixture
def overrides(monkeypatch, tmp_path) -> None:
    """Point the override tables at a single repo table with AV and ADM on L."""
    repo_data = tmp_path / "repo" / "data"
    repo_data.mkdir(parents=True)
    (repo_data / "scaling_overrides.json").write_text(json.dumps({"L": {"AV": 0.01, "ADM": 0.01, "*": 1}}))
    monkeypatch.setattr(th.config, "repo_root", tmp_path / "repo")
    monkeypatch.setattr(th.config, "data_root", repo_data)


def _cache(tmp_path: Path, name: str, closes: list[float]) -> Path:
    meta = tmp_path / "timeseries" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2026-10-19", periods=len(closes), freq="D")
    pd.DataFrame({"Date": dates, "Close": closes}).to_parquet(meta / f"{name}.parquet", index=False)
    return tmp_path / "timeseries"


def _snapshot(tmp_path: Path, prices: dict[str, float]) -> Path:
    path = tmp_path / "latest_prices.json"
    path.write_text(json.dumps({t: {"last_price": p, "price_currency": "GBP"} for t, p in prices.items()}))
    return path


def test_lists_ticker_specific_overrides_only(overrides) -> None:
    assert check.override_tickers() == [("ADM", "L"), ("AV", "L")]


def test_passes_when_snapshot_is_scaled(overrides, tmp_path, capsys) -> None:
    cache_dir = _cache(tmp_path, "AV_L", [480.0, 512.4])
    _cache(tmp_path, "ADM_L", [3588.0])
    snapshot = _snapshot(tmp_path, {"AV.L": 5.18, "ADM.L": 35.5})

    assert check.main([str(snapshot), str(cache_dir)]) == 0
    out = capsys.readouterr().out
    assert "::error::" not in out
    assert "OK AV.L" in out and "OK ADM.L" in out


def test_fails_when_snapshot_is_100x_too_high(overrides, tmp_path, capsys) -> None:
    cache_dir = _cache(tmp_path, "AV_L", [512.4])
    _cache(tmp_path, "ADM_L", [3588.0])
    snapshot = _snapshot(tmp_path, {"AV.L": 512.4, "ADM.L": 35.5})

    assert check.main([str(snapshot), str(cache_dir)]) == 1
    out = capsys.readouterr().out
    assert "::error::AV.L" in out
    assert "OK ADM.L" in out


def test_skips_ticker_absent_from_snapshot(overrides, tmp_path, capsys) -> None:
    cache_dir = _cache(tmp_path, "AV_L", [512.4])
    snapshot = _snapshot(tmp_path, {"AV.L": 5.12})

    assert check.main([str(snapshot), str(cache_dir)]) == 0
    assert "::notice::ADM.L has no price in the snapshot" in capsys.readouterr().out


def test_skips_ticker_without_cached_series(overrides, tmp_path, capsys) -> None:
    cache_dir = _cache(tmp_path, "AV_L", [512.4])
    snapshot = _snapshot(tmp_path, {"AV.L": 5.12, "ADM.L": 3588.0})

    assert check.main([str(snapshot), str(cache_dir)]) == 0
    assert "::notice::ADM.L has no cached series" in capsys.readouterr().out


def test_cache_file_matches_backend_naming(monkeypatch, tmp_path) -> None:
    from backend.timeseries import cache

    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    assert check.meta_cache_file(tmp_path, "av", "l") == Path(cache.meta_timeseries_cache_path("av", "l"))


def test_repo_table_covers_the_tickers_named_in_the_issue() -> None:
    pairs = set(check.override_tickers())
    assert {("AV", "L"), ("CLIG", "L"), ("HICL", "L"), ("ADM", "L")} <= pairs
