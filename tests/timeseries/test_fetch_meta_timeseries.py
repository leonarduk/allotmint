import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from backend.timeseries.fetch_meta_timeseries import (
    _coverage_ratio,
    _merge,
    _resolve_cache_exchange,
    _resolve_exchange_from_metadata,
    _resolve_loader_exchange,
    _resolve_ticker_exchange,
    _metadata_entry_exists,
    fetch_meta_timeseries,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


def _scenario_override_instruments_dir(meta, tmp_path, monkeypatch, _default_dir):
    data_root_instruments = tmp_path / "data" / "instruments"
    data_root_instruments.mkdir(parents=True)

    custom_dir = tmp_path / "custom_instruments"
    custom_dir.mkdir()

    monkeypatch.setattr(meta, "INSTRUMENTS_DIR", custom_dir)

    result = meta._instrument_dirs()
    assert result == [custom_dir.resolve()]


def _scenario_default_and_data_root(meta, tmp_path, monkeypatch, default_dir):
    data_root_instruments = tmp_path / "data" / "instruments"
    data_root_instruments.mkdir(parents=True)
    default_dir.mkdir(parents=True, exist_ok=True)

    result = meta._instrument_dirs()
    expected = [data_root_instruments.resolve(), default_dir.resolve()]
    assert result == expected


def _scenario_skip_broken_candidate(meta, tmp_path, monkeypatch, default_dir):
    data_root_instruments = tmp_path / "data" / "instruments"
    data_root_instruments.mkdir(parents=True)
    default_dir.mkdir(parents=True, exist_ok=True)

    sentinel = default_dir
    original_resolve = Path.resolve

    def flaky_resolve(self, *args, **kwargs):
        if self == sentinel:
            raise OSError("boom")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", flaky_resolve)

    result = meta._instrument_dirs()
    assert result == [data_root_instruments.resolve()]


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(_scenario_override_instruments_dir, id="custom_override_only"),
        pytest.param(_scenario_default_and_data_root, id="default_and_data_root"),
        pytest.param(_scenario_skip_broken_candidate, id="skip_broken_candidate"),
    ],
)
def test_instrument_dirs_handles_overrides(tmp_path, monkeypatch, scenario):
    import backend.timeseries.fetch_meta_timeseries as meta

    data_root = tmp_path / "data"
    monkeypatch.setattr(meta, "config", SimpleNamespace(data_root=data_root))

    default_dir = tmp_path / "default_instruments"
    default_dir.mkdir(parents=True)
    monkeypatch.setattr(meta, "_DEFAULT_INSTRUMENTS_DIR", default_dir)
    monkeypatch.setattr(meta, "INSTRUMENTS_DIR", default_dir)

    meta._resolve_exchange_from_metadata_cached.cache_clear()
    scenario(meta, tmp_path, monkeypatch, default_dir)
    meta._resolve_exchange_from_metadata_cached.cache_clear()


def test_resolve_exchange_from_metadata(tmp_path):
    instruments = tmp_path / "data" / "instruments" / "L"
    instruments.mkdir(parents=True)
    (instruments / "ABC.json").write_text("{}")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "INSTRUMENTS_DIR", tmp_path / "data" / "instruments"):
        assert meta._resolve_exchange_from_metadata("abc") == "L"
        assert meta._resolve_exchange_from_metadata("XYZ") == ""


@pytest.mark.parametrize(
    "ticker, exchange_arg, metadata_value, expected_exchange, expected_meta, log_substring",
    [
        (
            "ABC.L",
            "",
            "m",
            "L",
            "M",
            "Exchange metadata mismatch for ABC: using L but metadata M",
        ),
        (
            "ABC.L",
            "N",
            "L",
            "L",
            "L",
            "Exchange mismatch for ABC.L: suffix L vs argument N",
        ),
        (
            "XYZ",
            "",
            "l",
            "L",
            "L",
            "Resolved exchange for XYZ via metadata: L",
        ),
        (
            "XYZ",
            "N",
            "M",
            "N",
            "M",
            "Exchange metadata mismatch for XYZ: using N but metadata M",
        ),
    ],
)
def test_resolve_symbol_exchange_details(
    ticker,
    exchange_arg,
    metadata_value,
    expected_exchange,
    expected_meta,
    log_substring,
    caplog,
    monkeypatch,
):
    import backend.timeseries.fetch_meta_timeseries as meta

    captured_symbols: list[str] = []

    def _fake_resolve(symbol: str, value: str = metadata_value) -> str:
        captured_symbols.append(symbol)
        return value

    monkeypatch.setattr(meta, "_resolve_exchange_from_metadata", _fake_resolve)

    with caplog.at_level("DEBUG"):
        symbol, resolved_exchange, metadata_exchange = meta._resolve_symbol_exchange_details(
            ticker, exchange_arg
        )

    base_symbol = re.split(r"[._]", ticker, 1)[0]
    assert captured_symbols == [base_symbol]
    assert symbol == base_symbol.upper()
    assert resolved_exchange == expected_exchange
    assert metadata_exchange == expected_meta
    assert log_substring in caplog.text


def test_resolve_ticker_exchange_precedence():
    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "_resolve_exchange_from_metadata", return_value="Q"):
        # suffix beats exchange argument and metadata
        assert meta._resolve_ticker_exchange("ABC.L", "N") == ("ABC", "L")
        # argument beats metadata
        assert meta._resolve_ticker_exchange("ABC", "N") == ("ABC", "N")
        # metadata used when nothing else supplied
        assert meta._resolve_ticker_exchange("ABC", "") == ("ABC", "Q")


@pytest.mark.parametrize(
    "ticker, exchange_arg, resolved_exchange, expected",
    [
        ("ABC", "X", "", "X"),
        ("ABC", "X", "Q", "Q"),
        ("ABC.L", "", "", "L"),
        ("ABC", "", "M", "M"),
        ("ABC.L", "", "Q", "Q"),
        ("ABC", "", "", ""),
    ],
)
def test_resolve_loader_exchange(ticker, exchange_arg, resolved_exchange, expected):
    assert (
        _resolve_loader_exchange(ticker, exchange_arg, ticker.split(".")[0], resolved_exchange)
        == expected
    )


def test_metadata_entry_exists_requires_symbol_and_exchange(tmp_path):
    instruments_root = tmp_path / "instruments"
    (instruments_root / "L").mkdir(parents=True)
    (instruments_root / "L" / "ABC.json").write_text("{}")

    directories = (str(instruments_root),)

    assert _metadata_entry_exists("", "L", directories) is False
    assert _metadata_entry_exists("ABC", "", directories) is False


def test_metadata_entry_exists_skips_problem_directories(tmp_path, monkeypatch):
    broken_root = tmp_path / "broken"
    broken_root.mkdir()

    working_root = tmp_path / "working"
    (working_root / "L").mkdir(parents=True)
    (working_root / "L" / "ABC.json").write_text("{}")

    target_path = broken_root / "L" / "ABC.json"
    original_is_file = Path.is_file

    def flaky_is_file(self):
        if self == target_path:
            raise OSError("boom")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", flaky_is_file)

    directories = (str(broken_root), str(working_root))

    assert _metadata_entry_exists("abc", "l", directories) is True


@pytest.mark.parametrize(
    "ticker, exchange_arg, resolved_exchange, metadata_exchange, expected",
    [
        pytest.param("ABC", "X", "", "M", "X", id="explicit_override_wins"),
        pytest.param("ABC", "X", "", "", "X", id="provided_without_metadata"),
        pytest.param("ABC.L", "", "", "", "L", id="suffix_only"),
        pytest.param("ABC.L", "X", "L", "", "L", id="suffix_beats_argument"),
        pytest.param("ABC", "", "Q", "M", "M", id="metadata_conflict_defaults_to_metadata"),
        pytest.param("ABC.L", "", "L", "M", "M", id="metadata_conflict_with_suffix"),
        pytest.param("ABC", "", "Q", "", "", id="resolved_without_sources"),
    ],
)
def test_resolve_cache_exchange(
    ticker, exchange_arg, resolved_exchange, metadata_exchange, expected, caplog
):
    with caplog.at_level("DEBUG"):
        result = _resolve_cache_exchange(
            ticker,
            exchange_arg,
            ticker.split(".")[0],
            resolved_exchange,
            metadata_exchange,
        )

    assert result == expected
    if metadata_exchange and expected != metadata_exchange:
        assert "Cache exchange override" in caplog.text or "Cache exchange mismatch" in caplog.text


def test_merge_and_coverage_ratio():
    df1 = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]).date,
            "Open": [1, 2],
            "High": [1, 2],
            "Low": [1, 2],
            "Close": [1, 2],
            "Volume": [10, 20],
            "Ticker": ["ABC.L", "ABC.L"],
            "Source": ["A", "A"],
        }
    )

    df2 = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]).date,
            "Open": [2, 3],
            "High": [2, 3],
            "Low": [2, 3],
            "Close": [2, 3],
            "Volume": [20, 30],
            "Ticker": ["ABC.L", "ABC.L"],
            "Source": ["B", "B"],
        }
    )

    merged = _merge([df1, df2])
    assert merged["Date"].tolist() == list(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]).date)
    assert merged.iloc[1]["Source"] == "B"

    expected = set(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]).date)
    ratio = _coverage_ratio(merged, expected)
    assert ratio == pytest.approx(3 / 4)


def test_coverage_ratio_partial_and_empty():
    partial_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]).date,
        }
    )
    expected_dates = {
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
    }

    ratio = _coverage_ratio(partial_df, expected_dates)
    assert ratio == pytest.approx(2 / 3)
    assert ratio < 1.0

    empty_df = pd.DataFrame({"Date": pd.Series(dtype="datetime64[ns]")})
    assert _coverage_ratio(empty_df, expected_dates) == 0.0


def test_fetch_meta_timeseries_invalid_ticker():
    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "is_valid_ticker", return_value=False) as valid_mock, \
        patch.object(meta, "record_skipped_ticker") as record_mock, \
        patch.object(meta, "fetch_yahoo_timeseries_range") as yahoo_mock:
        df = meta.fetch_meta_timeseries("ABC", "L")

    assert df.empty
    yahoo_mock.assert_not_called()
    record_mock.assert_called_once_with("ABC", "L", reason="unknown")
    valid_mock.assert_called_once()


def _assert_cash_df(df, ticker, exchange, start, end):
    expected_dates = list(pd.bdate_range(start, end).date)
    assert df["Date"].tolist() == expected_dates
    assert (df[["Open", "High", "Low", "Close"]] == 1.0).all().all()
    assert (df["Volume"] == 0.0).all()
    assert (df["Ticker"] == f"{ticker}.{exchange}").all()
    assert (df["Source"] == "cash").all()


def test_fetch_meta_timeseries_cash_ticker():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    df = fetch_meta_timeseries("CASH", start_date=start, end_date=end)
    _assert_cash_df(df, "CASH", "", start, end)


def _make_df(dates, source, ticker="ABC.L"):
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates).date,
            "Open": [1] * len(dates),
            "High": [1] * len(dates),
            "Low": [1] * len(dates),
            "Close": [1] * len(dates),
            "Volume": [0] * len(dates),
            "Ticker": [ticker] * len(dates),
            "Source": [source] * len(dates),
        }
    )


def test_fetch_meta_timeseries_yahoo_only():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    yahoo_df = _make_df(["2024-01-01", "2024-01-02", "2024-01-03"], "Yahoo")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range") as stooq_mock, \
        patch.object(meta, "fetch_ft_df") as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    assert df.equals(yahoo_df)
    yahoo_mock.assert_called_once()
    stooq_mock.assert_not_called()
    ft_mock.assert_not_called()


def test_fetch_meta_timeseries_yahoo_stooq_merge():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    yahoo_df = _make_df(["2024-01-01", "2024-01-02"], "Yahoo")
    stooq_df = _make_df(["2024-01-03"], "Stooq")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range", return_value=stooq_df) as stooq_mock, \
        patch.object(meta, "fetch_ft_df") as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    assert df["Source"].tolist() == ["Yahoo", "Yahoo", "Stooq"]
    yahoo_mock.assert_called_once()
    stooq_mock.assert_called_once()
    ft_mock.assert_not_called()


def test_fetch_meta_timeseries_coverage_shortfall():
    start = date(2024, 1, 1)
    end = date(2024, 1, 4)
    yahoo_df = _make_df(["2024-01-01"], "Yahoo")
    stooq_df = _make_df(["2024-01-02"], "Stooq")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range", return_value=stooq_df) as stooq_mock, \
        patch.object(meta, "fetch_ft_df", return_value=pd.DataFrame(columns=STANDARD_COLUMNS)) as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    expected = set(pd.bdate_range(start, end).date)
    assert _coverage_ratio(df, expected) < 0.95
    yahoo_mock.assert_called_once()
    stooq_mock.assert_called_once()
    ft_mock.assert_called_once()


def test_fetch_meta_timeseries_min_coverage_threshold():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    yahoo_df = _make_df(["2024-01-01", "2024-01-02"], "Yahoo")

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "fetch_yahoo_timeseries_range", return_value=yahoo_df) as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range") as stooq_mock, \
        patch.object(meta, "fetch_ft_df") as ft_mock, \
        patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=False)):
        df = meta.fetch_meta_timeseries(
            "ABC", "L", start_date=start, end_date=end, min_coverage=0.5
        )

    assert df.equals(yahoo_df)
    yahoo_mock.assert_called_once()
    stooq_mock.assert_not_called()
    ft_mock.assert_not_called()


def test_fetch_meta_timeseries_isin_returns_ft_without_other_sources():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    ft_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]).date,
            "Open": [10.0, 10.5, 11.0],
            "High": [10.0, 10.5, 11.0],
            "Low": [10.0, 10.5, 11.0],
            "Close": [10.0, 10.5, 11.0],
            "Volume": [100, 110, 120],
            "Ticker": ["US1234567890"] * 3,
            "Source": ["FT"] * 3,
        }
    )

    import backend.timeseries.fetch_meta_timeseries as meta

    with patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(meta, "_is_isin", return_value=True) as isin_mock, \
        patch.object(meta, "fetch_ft_df", return_value=ft_df) as ft_mock, \
        patch.object(meta, "fetch_yahoo_timeseries_range") as yahoo_mock, \
        patch.object(meta, "fetch_stooq_timeseries_range") as stooq_mock, \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=True)):
        df = meta.fetch_meta_timeseries(
            "US1234567890", start_date=start, end_date=end
        )

    assert df.equals(ft_df)
    isin_mock.assert_called_once()
    ft_mock.assert_called_once_with("US1234567890", end, start)
    yahoo_mock.assert_not_called()
    stooq_mock.assert_not_called()


def test_fetch_meta_timeseries_alpha_vantage_rate_limit(monkeypatch):
    start = date(2024, 1, 1)
    end = date(2024, 1, 4)
    fallback_df = _make_df([
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ], "FT")

    import backend.timeseries.fetch_meta_timeseries as meta

    sleep_calls = []

    def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(meta.time, "sleep", fake_sleep)

    with patch.object(meta, "is_valid_ticker", return_value=True), \
        patch.object(
            meta,
            "fetch_yahoo_timeseries_range",
            return_value=pd.DataFrame(columns=STANDARD_COLUMNS),
        ) as yahoo_mock, \
        patch.object(
            meta,
            "fetch_stooq_timeseries_range",
            return_value=pd.DataFrame(columns=STANDARD_COLUMNS),
        ) as stooq_mock, \
        patch.object(
            meta,
            "fetch_alphavantage_timeseries_range",
            side_effect=meta.AlphaVantageRateLimitError("limit", retry_after=5),
        ) as av_mock, \
        patch.object(meta, "fetch_ft_df", return_value=fallback_df) as ft_mock, \
        patch.object(meta, "config", SimpleNamespace(alpha_vantage_enabled=True)):
        df = meta.fetch_meta_timeseries("ABC", "L", start_date=start, end_date=end)

    assert df.equals(fallback_df)
    assert sleep_calls == [5]
    yahoo_mock.assert_called_once()
    stooq_mock.assert_called_once()
    av_mock.assert_called_once()
    ft_mock.assert_called_once()

