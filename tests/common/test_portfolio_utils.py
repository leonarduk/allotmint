import json
import sys
import types
from datetime import datetime, timezone

import pandas as pd
import pytest

from backend.common import portfolio_utils as pu


def test_compute_var_valid_series():
    df = pd.DataFrame({"Close": [100, 110, 105, 95, 98]})
    var = pu.compute_var(df)
    assert var == pytest.approx(8.6015, rel=1e-3)


def test_compute_var_short_series_returns_none():
    df = pd.DataFrame({"Close": [100]})
    assert pu.compute_var(df) is None


def test_compute_var_empty_dataframe_returns_none():
    df = pd.DataFrame({"Close": []})
    assert pu.compute_var(df) is None


def test_compute_var_invalid_input_raises():
    with pytest.raises(AttributeError):
        pu.compute_var(123)  # type: ignore[arg-type]


def test_fx_to_base_same_currency(monkeypatch):
    called = {"count": 0}

    def fake_fetch(*args, **kwargs):  # pragma: no cover - should not be called
        called["count"] += 1
        return pd.DataFrame({"Rate": [1.0]})

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    rate = pu._fx_to_base("USD", "USD", {})
    assert rate == 1.0
    assert called["count"] == 0


def test_fx_to_base_foreign_currency(monkeypatch):
    df = pd.DataFrame({"Rate": [1.25]})
    monkeypatch.setattr(pu, "fetch_fx_rate_range", lambda *a, **k: df)
    cache: dict[str, float] = {}
    rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.25
    assert cache["USD"] == 1.25


def test_fx_to_base_uses_cached_rate(monkeypatch):
    called = {"count": 0}

    def fake_fetch(*args, **kwargs):  # pragma: no cover - should not be called
        called["count"] += 1
        return pd.DataFrame({"Rate": [1.3]})

    cache = {"USD": 1.3}
    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.3
    assert called["count"] == 0


def test_fx_to_base_fetch_failure_returns_one(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", boom)
    cache: dict[str, float] = {}
    with caplog.at_level("WARNING"):
        rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "Failed to fetch FX rate for USD" in caplog.text


def test_list_all_unique_tickers(monkeypatch):
    sample_portfolios = [
        {
            "owner": "alice",
            "accounts": [
                {"account_type": "isa", "holdings": [{"ticker": "AAA"}, {"ticker": "bbb"}]},
                {"account_type": "sipp", "holdings": [{"ticker": None}]},
            ],
        },
        {
            "owner": "bob",
            "accounts": [
                {"account_type": "taxable", "holdings": [{"ticker": "CCC"}]},
            ],
        },
    ]
    monkeypatch.setattr(pu, "list_portfolios", lambda: sample_portfolios)
    monkeypatch.setattr(pu, "list_virtual_portfolios", lambda: [])
    tickers = pu.list_all_unique_tickers()
    assert tickers == ["AAA", "BBB", "CCC"]


def test_refresh_snapshot_in_memory(monkeypatch):
    snapshot = {"AAA": {"price": 1}}
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT_TS", None)
    pu.refresh_snapshot_in_memory(snapshot, ts)
    assert pu._PRICE_SNAPSHOT == snapshot
    assert pu._PRICE_SNAPSHOT_TS == ts


def test_load_snapshot_missing_file(tmp_path, monkeypatch, caplog):
    path = tmp_path / "missing.json"
    monkeypatch.setattr(pu.config, "app_env", "local")
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)
    with caplog.at_level("WARNING"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert "Price snapshot not found" in caplog.text


def test_load_snapshot_malformed_json(tmp_path, monkeypatch, caplog):
    path = tmp_path / "bad.json"
    path.write_text("{bad json")
    monkeypatch.setattr(pu.config, "app_env", "local")
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)
    with caplog.at_level("ERROR"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert "Failed to parse snapshot" in caplog.text


def test_load_snapshot_aws_failure_falls_back_to_local(tmp_path, monkeypatch, caplog):
    payload = {"XYZ": {"price": 2}}
    path = tmp_path / "latest_prices.json"
    path.write_text(json.dumps(payload))

    class ClientError(Exception):
        pass

    class FakeS3:
        def get_object(self, Bucket, Key):  # noqa: N802
            raise ClientError("boom")

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeS3())
    fake_exc = types.SimpleNamespace(BotoCoreError=Exception, ClientError=ClientError)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)

    with caplog.at_level("ERROR"):
        data, returned_ts = pu._load_snapshot()

    assert data == payload
    assert returned_ts == datetime.fromtimestamp(path.stat().st_mtime)
    assert "Failed to fetch price snapshot" in caplog.text
