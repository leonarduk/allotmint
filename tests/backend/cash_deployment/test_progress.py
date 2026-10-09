"""Executed-vs-schedule tracking (#10480)."""

from __future__ import annotations

import json
from datetime import date

from backend.cash_deployment.bot import load_account_transactions
from backend.cash_deployment.progress import build_progress, buy_value_minor
from backend.cash_deployment.schedule import ScheduleInput


def _schedule(start: date) -> ScheduleInput:
    return ScheduleInput(account="isa", total_amount_minor=300_000, tranches=3, start_date=start)


def _buy(day: str, minor: int) -> dict:
    return {"date": day, "type": "BUY", "ticker": "VWX.L", "amount_minor": -minor}


def test_full_partial_and_missing_tranches(start):
    txs = [
        _buy("2026-01-10", 100_000),  # before the schedule started: never counted
        _buy("2026-01-20", 60_000),
        _buy("2026-02-01", 40_000),  # tranche 0 now 100%
        _buy("2026-02-20", 40_000),  # tranche 1 at 40%
    ]
    progress = build_progress(_schedule(start), txs, date(2026, 4, 20))
    statuses = [t["status"] for t in progress["tranches"]]
    assert statuses == ["done", "partly_done", "skipped"]
    assert [t["invested_minor"] for t in progress["tranches"]] == [100_000, 40_000, 0]
    assert progress["overdue_count"] == 2
    assert progress["deployed_minor"] == 140_000
    assert progress["remaining_minor"] == 160_000
    assert progress["summary"] == "2 tranches overdue, £1,600.00 still in cash vs £0.00 planned"


def test_open_window_is_due_then_upcoming(start):
    progress = build_progress(_schedule(start), [], date(2026, 1, 20))
    assert [t["status"] for t in progress["tranches"]] == ["due", "upcoming", "upcoming"]
    assert progress["current"]["index"] == 0
    assert progress["overdue_count"] == 0
    assert progress["summary"].startswith("On schedule")


def test_done_tranche_has_no_current(start):
    progress = build_progress(_schedule(start), [_buy("2026-01-16", 100_000)], date(2026, 1, 20))
    assert progress["current"] is None


def test_buys_after_as_of_are_ignored(start):
    progress = build_progress(_schedule(start), [_buy("2026-02-10", 100_000)], date(2026, 1, 20))
    assert progress["tranches"][0]["invested_minor"] == 0


def test_interest_since_start(start):
    txs = [
        {"date": "2026-01-01", "type": "INTEREST", "amount_minor": 999},
        {"date": "2026-01-31", "type": "INTEREST", "amount_minor": 1234},
        {"date": "2026-02-28", "type": "interest", "amount_minor": 1000},
    ]
    assert build_progress(_schedule(start), txs, date(2026, 3, 1))["interest_minor"] == 2234


def test_buy_value_falls_back_to_price_times_units():
    assert buy_value_minor({"type": "BUY", "price_gbp": 12.5, "units": 8, "fees": 1.5}) == 10_150
    assert buy_value_minor({"type": "BUY"}) == 0


def test_only_the_schedules_account_is_loaded(tmp_path):
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    (owner_dir / "ISA_transactions.json").write_text(json.dumps({"transactions": [_buy("2026-01-20", 1)]}))
    (owner_dir / "sipp_transactions.json").write_text(json.dumps({"transactions": [_buy("2026-01-20", 2)]}))
    rows = load_account_transactions("alex", "isa", tmp_path)
    assert [r["amount_minor"] for r in rows] == [-1]
    assert load_account_transactions("alex", "gia", tmp_path) == []
