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
