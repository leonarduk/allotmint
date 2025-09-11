from datetime import datetime, timezone

from backend.common import portfolio_utils as pu


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

