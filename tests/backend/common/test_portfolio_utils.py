import json
import sys
import types
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from backend.common import instrument_api as ia
from backend.common import portfolio_utils


def test_compute_var_with_normal_data():
    df = pd.DataFrame({"Close": [100, 102, 101, 105, 103]})

    result = portfolio_utils.compute_var(df, confidence=0.95)

    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    returns = closes.pct_change().dropna()
    expected = -np.quantile(returns, 0.05) * float(closes.iloc[-1])
    assert result == pytest.approx(expected)


def test_compute_var_with_insufficient_data():
    df = pd.DataFrame({"Close": [100]})

    assert portfolio_utils.compute_var(df) is None


def test_compute_var_with_non_numeric_input():
    df = pd.DataFrame({"Close": ["foo", "bar", None]})

    assert portfolio_utils.compute_var(df) is None


def test_fx_to_base_uses_fetched_rates(monkeypatch):
    cache: dict[str, float] = {}
    calls: list[tuple[str, str]] = []

    rate_map = {
        ("USD", "GBP"): pd.DataFrame({"Rate": [0.8]}),
        ("EUR", "GBP"): pd.DataFrame({"Rate": [0.9]}),
    }

    def fake_fetch(ccy: str, base: str, start, end):
        calls.append((ccy, base))
        return rate_map[(ccy, base)]

    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", fake_fetch)

    rate = portfolio_utils._fx_to_base("USD", "EUR", cache)

    assert rate == pytest.approx(0.8 / 0.9)
    assert ("USD", "GBP") in calls
    assert ("EUR", "GBP") in calls


def test_fx_to_base_falls_back_to_default_rate(monkeypatch):
    cache: dict[str, float] = {}

    def fake_fetch(ccy: str, base: str, start, end):
        if ccy == "JPY":
            raise RuntimeError("fetch failed")
        return pd.DataFrame()

    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", fake_fetch)

    rate = portfolio_utils._fx_to_base("JPY", "CAD", cache)

    assert rate == 1.0
    assert cache["JPY"] == 1.0
    assert cache["CAD"] == 1.0


def test_load_snapshot_from_s3(monkeypatch):
    data = {"AAPL": {"price": 123}}
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)

    class FakeBody:
        def read(self):
            return json.dumps(data).encode("utf-8")

    class FakeClient:
        def get_object(self, Bucket, Key):
            assert Bucket == "test-bucket"
            assert Key == portfolio_utils._PRICES_S3_KEY
            return {"Body": FakeBody(), "LastModified": timestamp}

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda service: FakeClient()

    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    exceptions_mod = types.ModuleType("botocore.exceptions")
    exceptions_mod.BotoCoreError = FakeBotoCoreError
    exceptions_mod.ClientError = FakeClientError

    botocore_mod = types.ModuleType("botocore")
    botocore_mod.exceptions = exceptions_mod

    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)

    monkeypatch.setenv(portfolio_utils.DATA_BUCKET_ENV, "test-bucket")
    monkeypatch.setattr(portfolio_utils.config, "app_env", "aws", raising=False)
    monkeypatch.setattr(portfolio_utils.config, "prices_json", None, raising=False)
    monkeypatch.setattr(portfolio_utils, "_PRICES_PATH", None, raising=False)

    result, ts = portfolio_utils._load_snapshot()

    assert result == data
    assert ts == timestamp


def test_load_snapshot_s3_failure_falls_back_to_local(monkeypatch, tmp_path):
    local_data = {"MSFT": {"price": 321}}
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(local_data))

    class FakeClient:
        def __init__(self, error_type):
            self._error_type = error_type

        def get_object(self, Bucket, Key):
            raise self._error_type("boom")

    fake_boto3 = types.ModuleType("boto3")

    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    exceptions_mod = types.ModuleType("botocore.exceptions")
    exceptions_mod.BotoCoreError = FakeBotoCoreError
    exceptions_mod.ClientError = FakeClientError

    botocore_mod = types.ModuleType("botocore")
    botocore_mod.exceptions = exceptions_mod

    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)

    fake_boto3.client = lambda service: FakeClient(FakeClientError)

    monkeypatch.setenv(portfolio_utils.DATA_BUCKET_ENV, "test-bucket")
    monkeypatch.setattr(portfolio_utils.config, "app_env", "aws", raising=False)
    monkeypatch.setattr(portfolio_utils.config, "prices_json", snapshot_path, raising=False)
    monkeypatch.setattr(portfolio_utils, "_PRICES_PATH", snapshot_path, raising=False)

    result, ts = portfolio_utils._load_snapshot()

    assert result == local_data
    assert ts is not None


def test_load_snapshot_local_missing_file(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing.json"

    monkeypatch.setattr(portfolio_utils.config, "app_env", None, raising=False)
    monkeypatch.setattr(portfolio_utils.config, "prices_json", missing_path, raising=False)
    monkeypatch.setattr(portfolio_utils, "_PRICES_PATH", missing_path, raising=False)

    result, ts = portfolio_utils._load_snapshot()

    assert result == {}
    assert ts is None


def test_first_nonempty_str_returns_trimmed_value():
    assert (
        portfolio_utils._first_nonempty_str(None, "   ", "  result  ", "other")
        == "result"
    )


def test_first_nonempty_str_returns_none_when_missing():
    assert portfolio_utils._first_nonempty_str("", "   ", None, 0) is None


def test_safe_num_parses_numeric_strings():
    assert portfolio_utils._safe_num("3.14") == pytest.approx(3.14)


def test_safe_num_returns_default_for_invalid():
    assert portfolio_utils._safe_num("not-a-number", default=7.5) == 7.5


def test_aggregate_by_ticker_uses_shared_grouping(monkeypatch):

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA.L",
                        "units": 1.0,
                        "market_value_gbp": 100.0,
                        "gain_gbp": 10.0,
                        "cost_gbp": 90.0,
                        "sector": "Technology",
                    },
                    {
                        "ticker": "BBB.L",
                        "units": 2.0,
                        "market_value_gbp": 50.0,
                        "gain_gbp": 5.0,
                        "cost_gbp": 45.0,
                        "currency": "USD",
                    },
                    {
                        "ticker": "CCC.L",
                        "units": 3.0,
                        "market_value_gbp": 75.0,
                        "gain_gbp": 15.0,
                        "cost_gbp": 60.0,
                        "region": "Europe",
                    },
                    {
                        "ticker": "DDD.L",
                        "units": 4.0,
                        "market_value_gbp": 25.0,
                        "gain_gbp": 2.0,
                        "cost_gbp": 23.0,
                    },
                ]
            }
        ]
    }

    definitions = {"shared": {"id": "shared", "name": "Shared Group"}}
    monkeypatch.setattr(ia, "list_group_definitions", lambda: definitions)
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda ticker, latest: (ticker.split(".")[0], "L"))
    monkeypatch.setattr(ia, "price_change_pct", lambda *args, **kwargs: None)

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(
        portfolio_utils,
        "get_instrument_meta",
        lambda t: {
            "name": "Shared",
            "currency": "GBP",
            "grouping_id": "shared",
            "grouping": "shared",
        },
    )
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda t: {})

    rows = portfolio_utils.aggregate_by_ticker(portfolio)
    assert rows[0]["grouping"] == "Shared Group"
    assert rows[0]["grouping_id"] == "shared"
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda ticker: {})
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda ticker: {})

    from backend.common import instrument_api

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda ticker, latest: (ticker, "L"))
    monkeypatch.setattr(instrument_api, "price_change_pct", lambda *args, **kwargs: None)

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    rows_by_ticker = {row["ticker"]: row for row in rows}

    assert "AAA.L" in rows_by_ticker
    assert rows_by_ticker["AAA.L"]["grouping"] == "Technology"
    assert rows_by_ticker["BBB.L"]["grouping"] == "USD"
    assert rows_by_ticker["CCC.L"]["grouping"] == "Europe"
    assert rows_by_ticker["DDD.L"]["grouping"] == "Unknown"
