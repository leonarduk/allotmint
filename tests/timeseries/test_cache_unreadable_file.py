"""An unreadable cache file is not mistaken for a cold cache and overwritten (#10975)."""

import importlib
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def _rows(dates) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": [1.0] * len(dates),
            "High": [2.0] * len(dates),
            "Low": [0.5] * len(dates),
            "Close": [1.5] * len(dates),
            "Volume": [100] * len(dates),
            "Ticker": ["ERNS"] * len(dates),
            "Source": ["Yahoo"] * len(dates),
        }
    )


def _refresh(cache, path: str) -> pd.DataFrame:
    def fetch(**kwargs):
        return _rows(pd.bdate_range(kwargs["start_date"], kwargs["end_date"]))

    return cache._rolling_cache(fetch, path, {}, days=20, ticker="ERNS", exchange="L")


def test_missing_file_is_a_cold_cache_and_is_written(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    path = cache._cache_path("meta", "ERNS_L.parquet")

    loaded = cache._load_parquet(path)
    assert loaded.empty and not loaded.attrs.get(cache._CACHE_READ_FAILED_ATTR)

    result = _refresh(cache, path)
    assert not result.empty
    assert len(pd.read_parquet(path)) == len(result)


def test_corrupt_file_is_logged_and_not_overwritten(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    path = cache._cache_path("meta", "ERNS_L.parquet")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"not a parquet file")

    with caplog.at_level(logging.WARNING, logger=cache.logger.name):
        result = _refresh(cache, path)

    assert not result.empty  # the fetch is still served
    assert Path(path).read_bytes() == b"not a parquet file"  # history left for repair
    assert "Could not read cache" in caplog.text
    assert "Not overwriting unreadable cache" in caplog.text


def test_readable_cache_still_merges_and_saves(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    yesterday = datetime.today().date() - timedelta(days=1)
    path = cache._cache_path("meta", "ERNS_L.parquet")
    cache._save_parquet(_rows(pd.bdate_range(end=yesterday, periods=30)[:-1]), path)

    _refresh(cache, path)

    assert len(pd.read_parquet(path)) == 30  # yesterday's row was fetched and stored
