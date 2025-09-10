import importlib
import sys
import warnings
from datetime import datetime, timedelta

import pandas as pd
from pandas.api.types import is_integer_dtype


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def test_merge_skips_empty_frames(monkeypatch, tmp_path):
    """Ensure merging works when existing cache is empty."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    def fetch_func(**_kwargs):
        today = datetime.today().date()
        data_date = today - timedelta(days=1)
        return pd.DataFrame(
            {
                "Date": [pd.Timestamp(data_date)],
                "Open": [1.0],
                "High": [2.0],
                "Low": [0.5],
                "Close": [1.5],
                "Volume": [100],
                "Ticker": ["ABC"],
                "Source": ["SRC"],
            }
        )

    cache_path = cache._cache_path("foo.parquet")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            "DataFrame concatenation with empty or all-NA entries is deprecated",
        )
        result = cache._rolling_cache(
            fetch_func,
            cache_path,
            {},
            days=2,
            ticker="ABC",
            exchange="L",
        )

    assert is_integer_dtype(result["Volume"])
    assert result["Volume"].iloc[0] == 100
