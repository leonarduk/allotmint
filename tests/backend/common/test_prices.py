"""Tests for :mod:`backend.common.prices`."""

from __future__ import annotations

import sys
import types
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.common import portfolio_utils, prices
from backend.common.portfolio_utils import PRICES_S3_KEY


def test_close_on_falls_back_to_close_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should use the first available close column."""

    sample_date = date(2024, 5, 6)
    frame = pd.DataFrame({"Close": [99.25]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)

    captured: list[tuple[str, str, date, date]] = []

    def fake_load(sym: str, exch: str, start_date: date, end_date: date):
        captured.append((sym, exch, start_date, end_date))
        return frame

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    result = prices._close_on("XYZ", "L", sample_date)

    assert result == pytest.approx(99.25)
    assert captured == [("XYZ", "L", sample_date, sample_date)]


def test_close_on_returns_none_when_no_price_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should return ``None`` if no recognised columns exist."""

    sample_date = date(2024, 5, 7)
    frame = pd.DataFrame({"open": [10.0], "high": [11.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(
        prices,
        "load_meta_timeseries_range",
        lambda sym, exch, start_date, end_date: frame,
    )

    assert prices._close_on("ABC", "N", sample_date) is None


def test_close_on_converts_native_currency_to_gbp(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should convert native close prices to GBP when needed."""

    sample_date = date(2024, 5, 8)
    frame = pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *args, **kwargs: frame)

    from backend.common import portfolio_utils

    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda *_: 0.8)
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta", lambda *_: {"currency": "USD"}
    )

    assert prices._close_on("USDX", "US", sample_date) == pytest.approx(80.0)


def test_close_on_converts_gbx_pence_to_gbp(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should apply pence->GBP conversion through CurrencyNormaliser."""

    sample_date = date(2024, 5, 8)
    frame = pd.DataFrame({"Close": [250.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *args, **kwargs: frame)
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta", lambda *_: {"currency": "GBX"}
    )

    # GBX conversion is arithmetic (/100); FX resolver must not be called.
    monkeypatch.setattr(
        portfolio_utils,
        "_fx_to_base",
        lambda *_: (_ for _ in ()).throw(AssertionError("_fx_to_base should not run for GBX")),
    )

    assert prices._close_on("VOD", "L", sample_date) == pytest.approx(2.5)


def test_get_price_snapshot_handles_stale_and_missing_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_price_snapshot`` should correctly combine live and cached data."""

    tickers = ["ABC.L", "DEF.N", "GHI.L"]
    now = datetime.now(UTC)
    stale_ts = now - timedelta(minutes=30)
    latest = {"ABC.L": 100.0, "DEF.N": 55.0, "GHI.L": 40.0}

    monkeypatch.setattr(prices, "_load_latest_prices", lambda requested: latest)
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda requested: {
            "ABC.L": {"price": 101.0, "timestamp": now},
            "DEF.N": {"price": 55.0, "timestamp": stale_ts},
        },
    )

    mapping = {"ABC.L": ("ABC", "L"), "DEF.N": ("DEF", "N"), "GHI.L": ("GHI", "L")}
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: mapping.get(full)
    )

    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    seven_day = last_trading_day - timedelta(days=7)
    thirty_day = last_trading_day - timedelta(days=30)

    close_lookup: dict[tuple[str, str, date], float | None] = {
        ("ABC", "L", seven_day): 95.0,
        ("ABC", "L", thirty_day): 90.0,
        ("DEF", "N", seven_day): None,
        ("DEF", "N", thirty_day): 50.0,
        ("GHI", "L", seven_day): 39.0,
        ("GHI", "L", thirty_day): 38.0,
    }

    requested: list[tuple[str, str, date]] = []

    def fake_close_on(sym: str, exch: str, requested_date: date):
        requested.append((sym, exch, requested_date))
        return close_lookup.get((sym, exch, requested_date))

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot(tickers)

    info_abc = snapshot["ABC.L"]
    assert info_abc["last_price"] == pytest.approx(101.0)
    assert info_abc["is_stale"] is False
    assert info_abc["last_price_time"] == now.isoformat().replace("+00:00", "Z")
    assert info_abc["last_price_date"] == last_trading_day.isoformat()
    assert info_abc["change_7d_pct"] == pytest.approx((101.0 / 95.0 - 1.0) * 100.0)
    assert info_abc["change_30d_pct"] == pytest.approx((101.0 / 90.0 - 1.0) * 100.0)

    info_def = snapshot["DEF.N"]
    assert info_def["last_price"] == pytest.approx(55.0)
    assert info_def["is_stale"] is True
    assert info_def["last_price_time"] == stale_ts.isoformat().replace("+00:00", "Z")
    assert info_def["change_7d_pct"] is None
    assert info_def["change_30d_pct"] == pytest.approx((55.0 / 50.0 - 1.0) * 100.0)

    info_ghi = snapshot["GHI.L"]
    assert info_ghi["last_price"] == pytest.approx(40.0)
    assert info_ghi["is_stale"] is True
    assert info_ghi["last_price_time"] is None
    assert info_ghi["change_7d_pct"] == pytest.approx((40.0 / 39.0 - 1.0) * 100.0)
    assert info_ghi["change_30d_pct"] == pytest.approx((40.0 / 38.0 - 1.0) * 100.0)


# ---------------------------------------------------------------------------
# refresh_prices() S3 upload behaviour
# ---------------------------------------------------------------------------


def _stub_refresh_prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Wire up minimal mocks so refresh_prices() can run without real data."""
    prices_file = tmp_path / "latest_prices.json"
    monkeypatch.setattr(prices.config, "prices_json", prices_file, raising=False)
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda tickers: {})
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", lambda s: None)
    monkeypatch.setattr(prices, "check_price_alerts", lambda: None)


def test_refresh_prices_uploads_to_s3_in_aws_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    """refresh_prices() must call s3.put_object with PRICES_S3_KEY when app_env==aws."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "aws", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    put_calls: list[dict] = []

    class FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    fake_boto3 = types.SimpleNamespace(client=lambda svc: FakeS3())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    import logging

    with caplog.at_level(logging.INFO):
        prices.refresh_prices()

    assert len(put_calls) == 1, f"Expected exactly one put_object call; got {put_calls}"
    assert put_calls[0]["Bucket"] == "test-bucket"
    assert put_calls[0]["Key"] == PRICES_S3_KEY
    assert "Uploaded price snapshot" in caplog.text


def test_refresh_prices_s3_upload_failure_logs_warning_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    """If the S3 upload fails, refresh_prices() must log WARNING and not re-raise."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "aws", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    class FakeS3:
        def put_object(self, **kwargs):
            raise OSError("network failure")

    fake_boto3 = types.SimpleNamespace(client=lambda svc: FakeS3())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    import logging

    with caplog.at_level(logging.WARNING):
        result = prices.refresh_prices()

    assert "Failed to upload price snapshot to S3" in caplog.text
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records == [], (
        f"S3 upload failure must log WARNING, not ERROR; got: {[r.message for r in error_records]}"
    )
    assert result is not None, "refresh_prices() must still return normally after S3 upload failure"


def test_refresh_prices_skips_s3_when_data_bucket_not_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    """refresh_prices() must log a WARNING and skip S3 when DATA_BUCKET env var is absent."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "aws", raising=False)
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    import logging

    with caplog.at_level(logging.WARNING):
        prices.refresh_prices()

    assert "DATA_BUCKET not set" in caplog.text


def test_refresh_prices_does_not_upload_to_s3_in_local_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """refresh_prices() must not call s3.put_object when app_env != 'aws'."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "local", raising=False)

    put_calls: list = []

    class FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    fake_boto3 = types.SimpleNamespace(client=lambda svc: FakeS3())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    prices.refresh_prices()

    assert put_calls == [], "S3 upload must not happen in non-AWS environments"


def test_build_securities_and_get_security_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security metadata should be derived from current portfolios."""

    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "abc", "name": "Alpha"},
                        {"ticker": "def"},
                        {"ticker": ""},
                        {},
                    ]
                }
            ]
        },
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "GHI", "name": "Gamma"},
                        {"ticker": None},
                    ]
                }
            ]
        },
    ]

    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)

    securities = prices._build_securities_from_portfolios()

    assert securities == {
        "ABC": {"ticker": "ABC", "name": "Alpha"},
        "DEF": {"ticker": "DEF", "name": "DEF"},
        "GHI": {"ticker": "GHI", "name": "Gamma"},
    }

    assert prices.get_security_meta("abc") == {"ticker": "ABC", "name": "Alpha"}
    assert prices.get_security_meta("DEF") == {"ticker": "DEF", "name": "DEF"}
    assert prices.get_security_meta("missing") is None


def test_last_close_fallback_snapshot_does_not_double_convert_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USD last-close fallback should remain single-converted when aggregated."""

    ticker = "USDX.US"
    monkeypatch.setattr(prices, "_load_latest_prices", lambda _: {ticker: 80.0})
    monkeypatch.setattr(prices, "load_live_prices", lambda _: {})
    monkeypatch.setattr(prices, "_close_on", lambda *_: 80.0)
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("USDX", "US")
    )

    snapshot = prices.get_price_snapshot([ticker])
    assert snapshot[ticker]["price_currency"] == "GBP"
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot, raising=False)
    monkeypatch.setattr(
        "backend.common.instrument_api._resolve_full_ticker", lambda t, _: ("USDX", "US")
    )
    monkeypatch.setattr(
        portfolio_utils, "get_instrument_meta", lambda _: {"currency": "USD", "name": "USD X"}
    )
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda _: {})
    monkeypatch.setattr("backend.common.instrument_api.price_change_pct", lambda *_: None)
    monkeypatch.setattr(
        portfolio_utils, "_fx_to_base", lambda c, b, cache: 0.8 if c == "USD" else 1.0
    )

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": ticker,
                        "exchange": "US",
                        "units": 2,
                        "cost_basis_gbp": 100.0,
                        "currency": "USD",
                    }
                ]
            }
        ]
    }

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert rows[0]["last_price_gbp"] == pytest.approx(80.0)
    assert rows[0]["market_value_gbp"] == pytest.approx(160.0)


def test_last_close_fallback_snapshot_marks_gbx_prices_as_gbp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GBX instruments should not be divided twice when snapshot uses last-close fallback."""

    ticker = "VOD.L"
    monkeypatch.setattr(prices, "_load_latest_prices", lambda _: {ticker: 1.103})
    monkeypatch.setattr(prices, "load_live_prices", lambda _: {})
    monkeypatch.setattr(prices, "_close_on", lambda *_: 1.103)
    monkeypatch.setattr(
        prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("VOD", "L")
    )

    snapshot = prices.get_price_snapshot([ticker])
    assert snapshot[ticker]["price_currency"] == "GBP"

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot, raising=False)
    monkeypatch.setattr(
        "backend.common.instrument_api._resolve_full_ticker", lambda t, _: ("VOD", "L")
    )
    monkeypatch.setattr(
        portfolio_utils,
        "get_instrument_meta",
        lambda _: {"currency": "GBX", "name": "Vodafone"},
    )
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda _: {"currency": "GBX"})
    monkeypatch.setattr("backend.common.instrument_api.price_change_pct", lambda *_: None)

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": ticker,
                        "exchange": "L",
                        "units": 290,
                        "cost_basis_gbp": 200.46,
                        "currency": "GBX",
                    }
                ]
            }
        ]
    }

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert rows[0]["last_price_gbp"] == pytest.approx(1.103)
    assert rows[0]["market_value_gbp"] == pytest.approx(319.87)
    assert rows[0]["gain_gbp"] == pytest.approx(119.41)


def test_close_on_returns_none_when_fx_lookup_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should return ``None`` when FX conversion cannot be resolved."""

    sample_date = date(2024, 5, 9)
    frame = pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *args, **kwargs: frame)

    from backend.common import portfolio_utils

    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda *_: None)
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta", lambda *_: {"currency": "USD"}
    )

    assert prices._close_on("USDX", "US", sample_date) is None
