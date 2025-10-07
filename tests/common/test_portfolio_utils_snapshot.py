import asyncio
import json
from datetime import datetime

import pandas as pd
import pytest

from backend.common import portfolio_utils as pu


def test_refresh_snapshot_in_memory_from_timeseries_writes_file(tmp_path, monkeypatch):
    tickers = ["FOO.L", "BAR.N"]
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {t: {} for t in tickers})
    monkeypatch.setattr(pu, "list_all_unique_tickers", lambda: tickers)

    foo_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "Close": [10.0, 11.0],
        }
    )
    bar_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "Close": [21.0, 22.0],
        }
    )
    frames = {"FOO": foo_df, "BAR": bar_df}

    def fake_load_meta_timeseries_range(*, ticker, exchange, start_date, end_date):
        return frames[ticker.upper()]

    monkeypatch.setattr(pu, "load_meta_timeseries_range", fake_load_meta_timeseries_range)
    monkeypatch.setattr(pu, "get_scaling_override", lambda ticker, exchange, meta: 1)

    scale_calls = []

    def fake_apply_scaling(df, scale):
        scale_calls.append(scale)
        return df

    monkeypatch.setattr(pu, "apply_scaling", fake_apply_scaling)

    refreshed = {}

    def fake_refresh_snapshot_in_memory(snapshot, timestamp):
        refreshed["snapshot"] = snapshot
        refreshed["timestamp"] = timestamp

    monkeypatch.setattr(pu, "refresh_snapshot_in_memory", fake_refresh_snapshot_in_memory)

    prices_path = tmp_path / "latest_prices.json"
    monkeypatch.setattr(pu, "_PRICES_PATH", prices_path)

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    assert scale_calls == [1, 1]
    expected_snapshot = {
        "FOO.L": {"last_price": 11.0, "last_price_date": "2024-01-02"},
        "BAR.N": {"last_price": 22.0, "last_price_date": "2024-01-03"},
    }
    assert refreshed["snapshot"] == expected_snapshot
    assert isinstance(refreshed["timestamp"], datetime)

    assert json.loads(prices_path.read_text()) == expected_snapshot


def test_refresh_snapshot_scaling_override_rescales_gbp(tmp_path, monkeypatch):
    tickers = ["GBX.L"]
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {t: {} for t in tickers})
    monkeypatch.setattr(pu, "list_all_unique_tickers", lambda: tickers)

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-03", "2024-01-04"]),
            "Close_gbp": [55.0, 60.0],
        }
    )

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries_range",
        lambda *, ticker, exchange, start_date, end_date: df,
    )

    monkeypatch.setattr(pu, "get_scaling_override", lambda ticker, exchange, meta: 0.5)

    scale_calls: list[float] = []

    def fake_apply_scaling(frame, scale):
        scale_calls.append(scale)
        return frame

    monkeypatch.setattr(pu, "apply_scaling", fake_apply_scaling)

    captured: dict[str, object] = {}

    def fake_refresh_snapshot_in_memory(snapshot, timestamp):
        captured["snapshot"] = snapshot
        captured["timestamp"] = timestamp

    monkeypatch.setattr(pu, "refresh_snapshot_in_memory", fake_refresh_snapshot_in_memory)

    prices_path = tmp_path / "latest_prices.json"
    monkeypatch.setattr(pu, "_PRICES_PATH", prices_path)

    pu.refresh_snapshot_in_memory_from_timeseries(days=2)

    assert scale_calls == [0.5]

    expected_snapshot = {
        "GBX.L": {"last_price": 30.0, "last_price_date": "2024-01-04"},
    }

    assert captured["snapshot"] == expected_snapshot
    assert json.loads(prices_path.read_text()) == expected_snapshot


def test_refresh_snapshot_logs_warning_when_timeseries_missing(tmp_path, monkeypatch, caplog):
    tickers = ["GOOD.L", "BAD.N"]
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {t: {} for t in tickers})
    monkeypatch.setattr(pu, "list_all_unique_tickers", lambda: tickers)

    good_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-02-01", "2024-02-02"]),
            "Close": [100.0, 101.0],
        }
    )

    def fake_load_meta_timeseries_range(*, ticker, exchange, start_date, end_date):
        if ticker == "GOOD":
            return good_df
        raise OSError("boom")

    monkeypatch.setattr(pu, "load_meta_timeseries_range", fake_load_meta_timeseries_range)
    monkeypatch.setattr(pu, "get_scaling_override", lambda *_, **__: 1)

    refreshed = {}

    def fake_refresh_snapshot_in_memory(snapshot, timestamp):
        refreshed["snapshot"] = snapshot

    monkeypatch.setattr(pu, "refresh_snapshot_in_memory", fake_refresh_snapshot_in_memory)

    prices_path = tmp_path / "latest_prices.json"
    monkeypatch.setattr(pu, "_PRICES_PATH", prices_path)

    caplog.set_level("WARNING")

    pu.refresh_snapshot_in_memory_from_timeseries(days=5)

    assert "Could not get timeseries for BAD.N" in "\n".join(caplog.messages)

    expected_snapshot = {
        "GOOD.L": {"last_price": 101.0, "last_price_date": "2024-02-02"},
    }

    assert refreshed["snapshot"] == expected_snapshot
    assert json.loads(prices_path.read_text()) == expected_snapshot


def test_refresh_snapshot_skips_write_when_path_missing(monkeypatch, caplog):
    tickers = ["SKIP.L"]
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {t: {} for t in tickers})
    monkeypatch.setattr(pu, "list_all_unique_tickers", lambda: tickers)

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-10"]),
            "Close": [12.0],
        }
    )

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries_range",
        lambda *, ticker, exchange, start_date, end_date: df,
    )
    monkeypatch.setattr(pu, "get_scaling_override", lambda *_, **__: 1)

    recorded = {}

    def fake_refresh_snapshot_in_memory(snapshot, timestamp):
        recorded["snapshot"] = snapshot

    monkeypatch.setattr(pu, "refresh_snapshot_in_memory", fake_refresh_snapshot_in_memory)
    monkeypatch.setattr(pu, "_PRICES_PATH", None)

    caplog.set_level("INFO")

    pu.refresh_snapshot_in_memory_from_timeseries(days=1)

    assert recorded["snapshot"] == {
        "SKIP.L": {"last_price": 12.0, "last_price_date": "2024-03-10"},
    }
    assert any(
        "Price snapshot path not configured; skipping write" in message for message in caplog.messages
    )

@pytest.mark.anyio("asyncio")
async def test_refresh_snapshot_async_invokes_to_thread(monkeypatch):
    calls = {}

    def fake_refresh(days):
        calls.setdefault("refresh", []).append(days)

    async def fake_to_thread(func, /, *args, **kwargs):
        calls["to_thread"] = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
        }
        return func(*args, **kwargs)

    async def fake_create_task(coro, *, name=None, context=None):
        calls["create_task"] = {
            "coro": coro,
            "name": name,
            "context": context,
        }
        return await coro

    monkeypatch.setattr(pu, "refresh_snapshot_in_memory_from_timeseries", fake_refresh)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    task = pu.refresh_snapshot_async(days=3)
    await task

    assert calls["refresh"] == [3]
    assert calls["to_thread"]["func"] is fake_refresh
    assert calls["to_thread"]["kwargs"] == {"days": 3}
