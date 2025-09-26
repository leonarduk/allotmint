import pandas as pd
import backend.timeseries.fetch_meta_timeseries as fmt
from unittest.mock import patch


def _df():
    return pd.DataFrame({"Date": [1], "Close": [2]})


def test_run_all_tickers_filters_and_delays(monkeypatch, caplog):
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        if sym == "AAA":
            return _df()
        if sym == "BBB":
            return pd.DataFrame()
        raise Exception("boom")

    monkeypatch.setattr(fmt.config, "stooq_requests_per_minute", 30, raising=False)
    sleep_calls = []
    monkeypatch.setattr(fmt.time, "sleep", lambda s: sleep_calls.append(s))

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        with caplog.at_level("WARNING", logger="meta_timeseries"):
            out = fmt.run_all_tickers(["AAA", "BBB", "CCC"], days=5)

    assert out == ["AAA"]
    assert calls == [("AAA", "", 5), ("BBB", "", 5), ("CCC", "", 5)]
    assert sleep_calls == [2.0, 2.0]
    assert "CCC" in caplog.text


def test_run_all_tickers_uses_suffix_and_argument_exchanges():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        fmt.run_all_tickers(["AAA.N", "BBB"], exchange="L", days=7)

    assert calls == [("AAA", "N", 7), ("BBB", "L", 7)]


def test_load_timeseries_data_filters_and_warnings(monkeypatch, caplog):
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        if sym == "AAA":
            return _df()
        if sym == "BBB":
            return pd.DataFrame()
        raise Exception("fail")

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        with caplog.at_level("WARNING", logger="meta_timeseries"):
            out = fmt.load_timeseries_data(["AAA", "BBB", "CCC"], days=5)

    assert list(out.keys()) == ["AAA"]
    assert calls == [("AAA", "", 5), ("BBB", "", 5), ("CCC", "", 5)]
    assert "CCC" in caplog.text


def test_load_timeseries_data_uses_suffix_and_argument_exchanges():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        fmt.load_timeseries_data(["AAA.N", "BBB"], exchange="L", days=3)

    assert calls == [("AAA", "N", 3), ("BBB", "L", 3)]
