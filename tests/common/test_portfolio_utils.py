import json
import sys
import types
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from backend.common import portfolio_utils as pu


def test_compute_var_with_valid_data():
    df = pd.DataFrame({"Close": [100, 105, 102, 110]})

    result = pu.compute_var(df)

    closes = df["Close"].astype(float)
    returns = closes.pct_change().dropna().to_numpy()
    expected = -np.quantile(returns, 0.05) * closes.iloc[-1]

    assert result == pytest.approx(expected)


def test_compute_var_returns_none_for_empty_dataframe():
    df = pd.DataFrame(columns=["Close"])

    assert pu.compute_var(df) is None


def test_compute_var_returns_none_when_close_missing():
    df = pd.DataFrame({"Open": [100, 101, 102]})

    assert pu.compute_var(df) is None


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("42.5", 0.0, 42.5),
        ("invalid", 1.23, 1.23),
        (None, -5.0, -5.0),
    ],
)
def test_safe_num_handles_various_inputs(value, default, expected):
    assert pu._safe_num(value, default) == expected


def test_first_nonempty_str_skips_blank_candidates():
    result = pu._first_nonempty_str("", "   ", None, "  ticker ", "fallback")

    assert result == "ticker"


def test_first_nonempty_str_with_source_returns_trimmed_value():
    result = pu._first_nonempty_str_with_source(
        ("yahoo", "  value  "),
        ("manual", ""),
        ("fallback", None),
    )

    assert result == ("value", "yahoo")


def test_first_nonempty_str_with_source_returns_none_when_missing():
    result = pu._first_nonempty_str_with_source(
        ("primary", "  "),
        ("secondary", None),
        ("tertiary", 0),
        ("quaternary", []),
        ("quinary", "\n"),
    )

    assert result == (None, None)


def test_fx_to_base_uses_cache_for_currency_and_base(monkeypatch):
    rates = {"JPY": 0.005, "USD": 0.8}
    calls: list[tuple[str, str]] = []

    def fake_fetch(base: str, quote: str, start, end):
        calls.append((base, quote))
        return pd.DataFrame({"Rate": [rates[base]]})

    cache: dict[str, float] = {}
    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)

    rate_first = pu._fx_to_base("jpy", "usd", cache)

    expected = rates["JPY"] / rates["USD"]
    assert rate_first == pytest.approx(expected)
    assert cache == {"JPY": rates["JPY"], "USD": rates["USD"]}
    assert calls == [("JPY", "GBP"), ("USD", "GBP")]

    rate_second = pu._fx_to_base("JPY", "USD", cache)

    assert rate_second == pytest.approx(expected)
    assert calls == [("JPY", "GBP"), ("USD", "GBP")]


def test_fx_to_base_returns_identity_when_currency_matches_base(monkeypatch):
    called: list[tuple] = []

    def fake_fetch(*args, **kwargs):  # pragma: no cover - defensive
        called.append(args)
        return pd.DataFrame({"Rate": [1.0]})

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)

    rate = pu._fx_to_base("usd", "USD", {})

    assert rate == 1.0
    assert called == []


def test_load_snapshot_falls_back_to_local_file(tmp_path, monkeypatch, caplog):
    payload = {"ABC": {"price": 123}}
    local_path = tmp_path / "latest_prices.json"
    local_path.write_text(json.dumps(payload))

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setattr(pu.config, "prices_json", local_path)
    monkeypatch.setattr(pu, "_PRICES_PATH", local_path)
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")

    class ClientError(Exception):
        pass

    class FakeS3Client:
        def get_object(self, Bucket, Key):  # noqa: N803
            raise ClientError("boom")

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda service: FakeS3Client()
    fake_exceptions = types.SimpleNamespace(BotoCoreError=Exception, ClientError=ClientError)
    fake_botocore = types.ModuleType("botocore")
    fake_botocore.exceptions = fake_exceptions

    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exceptions)

    with caplog.at_level("ERROR"):
        data, timestamp = pu._load_snapshot()

    assert data == payload
    assert timestamp == datetime.fromtimestamp(local_path.stat().st_mtime)
    assert "Failed to fetch price snapshot" in caplog.text
