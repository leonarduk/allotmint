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

    monkeypatch.setattr(
        fmt,
        "_resolve_exchange_from_metadata",
        lambda *_args, **_kwargs: "",
    )
    fmt._resolve_exchange_from_metadata_cached.cache_clear()
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


def test_run_all_tickers_prefers_metadata_exchange_for_cache():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        with patch.object(
            fmt,
            "_resolve_exchange_from_metadata",
            side_effect=["L", ""],
        ):
            fmt.run_all_tickers(["AAA.N", "BBB"], exchange="Q", days=7)

    assert calls == [("AAA", "L", 7), ("BBB", "Q", 7)]


def test_run_all_tickers_resets_cache_exchange_after_metadata_removed(monkeypatch, tmp_path):
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    monkeypatch.setattr(fmt, "INSTRUMENTS_DIR", tmp_path / "instruments")
    instruments_dir = fmt.INSTRUMENTS_DIR / "L"
    instruments_dir.mkdir(parents=True)
    (instruments_dir / "AAA.json").write_text("{}", encoding="utf-8")

    fmt._resolve_exchange_from_metadata_cached.cache_clear()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        fmt.run_all_tickers(["AAA"], days=5)

    assert calls == [("AAA", "L", 5)]

    calls.clear()
    (instruments_dir / "AAA.json").unlink()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        fmt.run_all_tickers(["AAA"], days=5)

    assert calls == [("AAA", "", 5)]


def test_run_all_tickers_drops_cached_exchange_when_metadata_blank():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    fmt._resolve_exchange_from_metadata_cached.cache_clear()

    with patch.object(fmt, "_resolve_exchange_from_metadata", return_value="L"):
        with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
            fmt.run_all_tickers(["AAA"], days=5)

    assert calls == [("AAA", "L", 5)]

    calls.clear()
    fmt._resolve_exchange_from_metadata_cached.cache_clear()

    with patch.object(fmt, "_resolve_exchange_from_metadata", return_value=""):
        with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
            fmt.run_all_tickers(["AAA"], days=5)

    assert calls == [("AAA", "", 5)]


def test_load_timeseries_data_filters_and_warnings(monkeypatch, caplog):
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        if sym == "AAA":
            return _df()
        if sym == "BBB":
            return pd.DataFrame()
        raise Exception("fail")

    monkeypatch.setattr(
        fmt,
        "_resolve_exchange_from_metadata",
        lambda *_args, **_kwargs: "",
    )
    fmt._resolve_exchange_from_metadata_cached.cache_clear()
    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        with caplog.at_level("WARNING", logger="meta_timeseries"):
            out = fmt.load_timeseries_data(["AAA", "BBB", "CCC"], days=5)

    assert list(out.keys()) == ["AAA"]
    assert calls == [("AAA", "", 5), ("BBB", "", 5), ("CCC", "", 5)]
    assert "CCC" in caplog.text


def test_load_timeseries_data_prefers_metadata_exchange_for_cache():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        with patch.object(
            fmt,
            "_resolve_exchange_from_metadata",
            side_effect=["N", ""],
        ):
            fmt.load_timeseries_data(["AAA.L", "BBB"], exchange="L", days=3)

    assert calls == [("AAA", "N", 3), ("BBB", "L", 3)]


def test_load_timeseries_data_handles_stale_metadata(monkeypatch, tmp_path):
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    monkeypatch.setattr(fmt, "INSTRUMENTS_DIR", tmp_path / "instruments")
    instruments_dir = fmt.INSTRUMENTS_DIR / "L"
    instruments_dir.mkdir(parents=True)
    (instruments_dir / "AAA.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(fmt.config, "data_root", tmp_path, raising=False)
    fmt._resolve_exchange_from_metadata_cached.cache_clear()
    assert fmt._resolve_exchange_from_metadata("AAA") == "L"

    (instruments_dir / "AAA.json").unlink()

    with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
        fmt.load_timeseries_data(["AAA"], days=5)

    assert calls == [("AAA", "", 5)]


def test_load_timeseries_data_drops_cached_exchange_when_metadata_blank():
    calls = []

    def fake_load(sym, ex, days):
        calls.append((sym, ex, days))
        return _df()

    fmt._resolve_exchange_from_metadata_cached.cache_clear()

    with patch.object(fmt, "_resolve_exchange_from_metadata", return_value="L"):
        with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
            fmt.load_timeseries_data(["AAA"], days=5)

    assert calls == [("AAA", "L", 5)]

    calls.clear()
    fmt._resolve_exchange_from_metadata_cached.cache_clear()

    with patch.object(fmt, "_resolve_exchange_from_metadata", return_value=""):
        with patch("backend.timeseries.cache.load_meta_timeseries", side_effect=fake_load):
            fmt.load_timeseries_data(["AAA"], days=5)

    assert calls == [("AAA", "", 5)]
