"""Future-dated transaction rows are left out of current holdings (#10903)."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import pytest

from backend.common.holdings_rebuild import (
    drop_future_dated,
    rebuild_holdings_document,
    replay_cutoff,
    transaction_cost_hints,
)
from backend.common.transaction_reconciliation import (
    _ledger_for,
    reconcile_transactions_with_holdings,
)
from backend.routes.transactions import _replayed_units

TODAY = date.today()


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _buy(units: float, pounds: float, day: str | None) -> dict:
    row = {"type": "BUY", "ticker": "MSFT.N", "units": units, "amount_minor": round(pounds * 100)}
    if day is not None:
        row["date"] = day
    return row


def _msft(doc: dict) -> dict:
    return next(h for h in doc["holdings"] if h["ticker"] == "MSFT.N")


def test_cutoff_is_tomorrow_unless_as_of_given() -> None:
    assert replay_cutoff() == _day(1)
    assert replay_cutoff(date(2025, 6, 30)) == "2025-06-30"


def test_drop_future_dated_keeps_undated_and_slack_rows(caplog: pytest.LogCaptureFixture) -> None:
    rows = [_buy(1, 1, _day(-1)), _buy(1, 1, _day(1)), _buy(1, 1, _day(2)), _buy(1, 1, None)]
    caplog.set_level(logging.WARNING, logger="backend.common.holdings_rebuild")

    kept = drop_future_dated(rows)

    assert kept == [rows[0], rows[1], rows[3]]
    assert "dated " + _day(2) in caplog.text


def test_stored_future_row_does_not_count_in_rebuilt_holding() -> None:
    tx = {"transactions": [_buy(10, 3_000.00, "2025-03-01"), _buy(1, 400.00, "2027-01-01")]}
    # The state a rebuild left behind before the fix: the future BUY counted.
    stale = {"ticker": "MSFT.N", "units": 11, "cost_basis_gbp": 3400, "acquired_date": "2027-01-01"}
    existing = {"holdings": [stale]}

    msft = _msft(rebuild_holdings_document(tx, "steve", "isa", existing, as_of=date(2026, 10, 15)))

    assert msft["units"] == pytest.approx(10)
    assert msft["cost_basis_gbp"] == pytest.approx(3_000.00)
    assert msft["acquired_date"] == "2025-03-01"


def test_stale_future_acquired_date_is_cleared_when_no_dated_row_remains() -> None:
    tx = {"transactions": [_buy(10, 3_000.00, None), _buy(1, 400.00, _day(30))]}
    existing = {"holdings": [{"ticker": "MSFT.N", "units": 11, "acquired_date": _day(30)}]}

    msft = _msft(rebuild_holdings_document(tx, "steve", "isa", existing))

    assert msft["units"] == pytest.approx(10)
    assert "acquired_date" not in msft


def test_as_of_counts_rows_up_to_that_date() -> None:
    tx = {"transactions": [_buy(10, 3_000.00, "2025-03-01"), _buy(1, 400.00, "2027-01-01")]}

    msft = _msft(rebuild_holdings_document(tx, "steve", "isa", as_of=date(2027, 1, 1)))

    assert msft["units"] == pytest.approx(11)
    assert msft["acquired_date"] == "2027-01-01"


def test_instrument_only_in_future_rows_is_carried_forward_not_removed() -> None:
    tx = {"transactions": [_buy(1, 400.00, _day(30))]}
    existing = {"holdings": [{"ticker": "MSFT.N", "units": 5, "cost_basis_gbp": 1_500.00}]}

    msft = _msft(rebuild_holdings_document(tx, "steve", "isa", existing))

    assert msft == {"ticker": "MSFT.N", "units": 5, "cost_basis_gbp": 1_500.00}


def test_cost_hints_ignore_future_rows() -> None:
    hints = transaction_cost_hints([_buy(10, 3_000.00, _day(-10)), _buy(1, 400.00, _day(30))])

    assert hints["MSFT.N"] == (3_000.00, None)


def test_opening_balance_offset_ignores_future_rows() -> None:
    rows = [_buy(10, 3_000.00, _day(-10)), _buy(1, 400.00, _day(30))]

    assert _replayed_units(rows, [], "MSFT.N") == pytest.approx(10)


def test_reconciler_ledger_ignores_future_rows() -> None:
    rows = [_buy(10, 3_000.00, _day(-10)), _buy(1, 400.00, _day(30))]

    assert _ledger_for({"transactions": rows}, rows)["MSFT.N"] == pytest.approx(10)


def test_stale_cost_including_future_row_is_not_carried_forward() -> None:
    # Undated remaining row has no known cost, so the cost falls back to the
    # previous holding only when its units match -- the stale 11 never does.
    opening = {"type": "TRANSFER_IN", "ticker": "MSFT.N", "units": 10}
    tx = {"transactions": [opening, _buy(1, 400.00, _day(30))]}
    existing = {"holdings": [{"ticker": "MSFT.N", "units": 11, "cost_basis_gbp": 3400}]}

    msft = _msft(rebuild_holdings_document(tx, "steve", "isa", existing))

    assert msft["units"] == pytest.approx(10)
    assert msft["cost_basis_gbp"] == 0.0


def test_reconciler_injects_no_synthetic_trade_for_future_row(tmp_path) -> None:
    owner_dir = tmp_path / "steve"
    owner_dir.mkdir()
    holding = {"ticker": "MSFT.N", "units": 10}
    holdings = {"owner": "steve", "account_type": "ISA", "holdings": [holding]}
    rows = [_buy(10, 3_000.00, _day(-10)), _buy(1, 400.00, _day(30))]
    (owner_dir / "isa.json").write_text(json.dumps(holdings))
    tx_path = owner_dir / "isa_transactions.json"
    tx_path.write_text(json.dumps({"owner": "steve", "account_type": "ISA", "transactions": rows}))

    reconcile_transactions_with_holdings(tmp_path)

    assert json.loads(tx_path.read_text())["transactions"] == rows


def test_reconciler_leaves_holdings_rebuilt_before_the_fix_alone(tmp_path) -> None:
    # isa.json still says 11: it was rebuilt while the future BUY counted.
    owner_dir = tmp_path / "steve"
    owner_dir.mkdir()
    holding = {"ticker": "MSFT.N", "units": 11}
    holdings = {"owner": "steve", "account_type": "ISA", "holdings": [holding]}
    rows = [_buy(10, 3_000.00, _day(-10)), _buy(1, 400.00, _day(30))]
    (owner_dir / "isa.json").write_text(json.dumps(holdings))
    tx_path = owner_dir / "isa_transactions.json"
    tx_path.write_text(json.dumps({"owner": "steve", "account_type": "ISA", "transactions": rows}))

    reconcile_transactions_with_holdings(tmp_path)

    assert json.loads(tx_path.read_text())["transactions"] == rows
