import pandas as pd
from unittest.mock import patch

from backend.timeseries.fetch_meta_timeseries import run_all_tickers


def test_run_all_tickers_accepts_full_tickers():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        # Non-empty dataframe signals success
        return pd.DataFrame({"Date": [1], "Close": [2]})

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        out = run_all_tickers(["AAA.L", "BBB"], exchange="N", days=10)

    assert out == ["AAA.L", "BBB"]
    assert calls == [("AAA", "L", 10), ("BBB", "N", 10)]


def test_run_all_tickers_handles_underscore_and_dot():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return pd.DataFrame({"Date": [1], "Close": [2]})

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        out = run_all_tickers(["ADBE_N", "AZN.L"], exchange="Q", days=5)

    assert out == ["ADBE_N", "AZN.L"]
    assert calls == [("ADBE", "N", 5), ("AZN", "L", 5)]


def test_run_all_tickers_resolves_exchange_from_metadata():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return pd.DataFrame({"Date": [1], "Close": [2]})

    with patch("backend.timeseries.fetch_meta_timeseries._resolve_exchange_from_metadata", return_value="L") as meta, \
         patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        out = run_all_tickers(["GSK"], days=3)

    assert out == ["GSK"]
    assert calls == [("GSK", "L", 3)]
    meta.assert_called_once_with("GSK")

