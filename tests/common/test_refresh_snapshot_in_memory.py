import json
import math
from datetime import datetime, timezone
from unittest.mock import Mock

from backend.common import portfolio_utils as pu
from backend.common import prices


def test_refresh_snapshot_in_memory_updates_globals(monkeypatch):
    initial = {"ABC": {"price": 1}}
    ts_initial = datetime(2023, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", initial.copy())
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT_TS", ts_initial)

    new_snapshot = {"XYZ": {"price": 2}}
    ts_new = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pu.refresh_snapshot_in_memory(new_snapshot, ts_new)

    assert pu._PRICE_SNAPSHOT == new_snapshot
    assert pu._PRICE_SNAPSHOT_TS == ts_new


def test_refresh_snapshot_in_memory_loads_when_none(monkeypatch):
    expected = {"DEF": {"price": 3}}
    ts = datetime(2024, 5, 1, tzinfo=timezone.utc)

    def fake_load():
        return expected, ts

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT_TS", None)
    monkeypatch.setattr(pu, "_load_snapshot", fake_load)

    pu.refresh_snapshot_in_memory()

    assert pu._PRICE_SNAPSHOT == expected
    assert pu._PRICE_SNAPSHOT_TS == ts


def test_refresh_snapshot_in_memory_stores_exactly_what_it_is_given(monkeypatch):
    """``refresh_snapshot_in_memory`` itself performs no NaN filtering — it is
    a thin write-through to the module-level globals. The NaN guard lives
    upstream (in ``refresh_prices``'s ``to_persist`` filter), so this
    function must faithfully persist whatever dict it receives, including a
    NaN, so that a regression in the upstream guard would be immediately
    visible here (defense-in-depth: this test pins the "dumb writer"
    contract that the upstream guard depends on)."""

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT_TS", None)

    poisoned = {"NAN.L": {"last_price": float("nan")}}
    ts = datetime(2024, 6, 1, tzinfo=timezone.utc)

    pu.refresh_snapshot_in_memory(poisoned, ts)

    assert math.isnan(pu._PRICE_SNAPSHOT["NAN.L"]["last_price"])
    assert pu._PRICE_SNAPSHOT_TS == ts


def test_refresh_prices_write_boundary_guard_prevents_nan_reaching_in_memory_snapshot(tmp_path, monkeypatch) -> None:
    """Defense-in-depth: ``refresh_prices`` must never hand a NaN/zero/negative
    price to ``refresh_snapshot_in_memory``. The ``to_persist`` filter at the
    write boundary (backend/common/prices.py) is what protects the in-memory
    snapshot from ever holding a non-finite or non-positive price, since
    ``refresh_snapshot_in_memory`` itself does not filter (see the sibling
    test above)."""

    seed = {"NAN.L": {"last_price": 42.0, "price_currency": "GBP"}}
    output_path = tmp_path / "prices.json"
    output_path.write_text(json.dumps(seed))

    snapshot = {
        "NAN.L": {"last_price": float("nan"), "price_currency": "GBP", "is_stale": True},
        "ZERO.L": {"last_price": 0.0, "price_currency": "GBP", "is_stale": True},
        "NEG.L": {"last_price": -5.0, "price_currency": "GBP", "is_stale": True},
        "OK.L": {"last_price": 12.0, "price_currency": "GBP", "is_stale": False},
    }

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: list(snapshot))
    monkeypatch.setattr(prices, "get_price_snapshot", lambda _: snapshot)
    monkeypatch.setattr(prices, "check_price_alerts", Mock())
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    captured: list = []
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", lambda merged: captured.append(merged))

    prices.refresh_prices()

    assert len(captured) == 1
    merged = captured[0]

    # NaN/zero/negative prices must never reach the in-memory write boundary.
    assert not math.isnan(merged["NAN.L"]["last_price"])
    assert merged["NAN.L"]["last_price"] == 42.0  # preserved seed value
    assert "ZERO.L" not in merged
    assert "NEG.L" not in merged
    assert merged["OK.L"]["last_price"] == 12.0
