"""Tests for pension pot snapshot persistence."""

import datetime as dt

import pytest

from backend.common import pension_snapshots as snapshots_mod
from backend.common.storage import get_storage


@pytest.fixture
def snapshot_storage(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'pension_snapshots.json'}")
    storage.save({})
    monkeypatch.setattr(snapshots_mod, "_STORAGE", storage)
    return storage


def test_get_previous_snapshot_returns_none_when_absent(snapshot_storage) -> None:
    assert snapshots_mod.get_previous_snapshot("alice") is None


def test_record_snapshot_first_time_uses_current_pot_as_baseline(snapshot_storage) -> None:
    today = dt.date(2024, 6, 1)
    snapshots_mod.record_snapshot("alice", pot_gbp=10000, as_of=today)

    stored = snapshots_mod.get_previous_snapshot("alice")
    assert stored == {
        "year": 2024,
        "start_of_year_pot_gbp": 10000,
        "last_pot_gbp": 10000,
        "last_as_of": "2024-06-01",
    }


def test_record_snapshot_same_year_keeps_start_of_year_baseline(snapshot_storage) -> None:
    snapshots_mod.record_snapshot("alice", pot_gbp=10000, as_of=dt.date(2024, 1, 5))
    snapshots_mod.record_snapshot("alice", pot_gbp=10500, as_of=dt.date(2024, 6, 1))

    stored = snapshots_mod.get_previous_snapshot("alice")
    assert stored["start_of_year_pot_gbp"] == 10000
    assert stored["last_pot_gbp"] == 10500


def test_record_snapshot_year_rollover_resets_baseline_to_last_pot(snapshot_storage) -> None:
    snapshots_mod.record_snapshot("alice", pot_gbp=10000, as_of=dt.date(2024, 12, 20))
    snapshots_mod.record_snapshot("alice", pot_gbp=10800, as_of=dt.date(2025, 1, 4))

    stored = snapshots_mod.get_previous_snapshot("alice")
    assert stored["year"] == 2025
    assert stored["start_of_year_pot_gbp"] == 10000
    assert stored["last_pot_gbp"] == 10800


def test_ytd_baseline_pot_gbp_no_previous_uses_current() -> None:
    baseline = snapshots_mod.ytd_baseline_pot_gbp(None, 5000, dt.date(2024, 1, 1))
    assert baseline == 5000


def test_previous_period_pot_gbp_no_previous_uses_current() -> None:
    assert snapshots_mod.previous_period_pot_gbp(None, 5000) == 5000


def test_previous_period_pot_gbp_returns_last_pot() -> None:
    previous = {"last_pot_gbp": 4200}
    assert snapshots_mod.previous_period_pot_gbp(previous, 5000) == 4200
