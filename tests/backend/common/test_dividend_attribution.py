"""Estimated dividends covered by booked income are never counted twice (#11086)."""

from __future__ import annotations

import copy
from datetime import date

import pandas as pd
import pytest

from backend.common import holdings_rebuild
from backend.common import ledger_performance as lp
from backend.common.dividend_attribution import (
    ATTRIBUTION_ONLY_KEY,
    booked_income_cutoff,
    is_attribution_only,
    is_estimated_dividend,
    mark_attribution_only,
)
from backend.common.position_returns import position_returns

SWEEP = {"type": "DIVIDEND", "date": "2026-08-10", "amount_minor": 160815, "comments": "Transfer from Income Account"}


def _estimate(day: str, ticker: str = "SEGA.L", amount_minor: int = 49497, **extra) -> dict:
    return {
        "type": "DIVIDEND",
        "ticker": ticker,
        "date": day,
        "amount_minor": amount_minor,
        "reason": "Automated dividend import",
        **extra,
    }


def test_estimates_are_recognised_by_flag_or_legacy_reason():
    assert is_estimated_dividend(_estimate("2026-07-16"))
    assert is_estimated_dividend({"type": "DIVIDEND", "ticker": "X.L", "estimated": True})
    assert not is_estimated_dividend(SWEEP)
    assert not is_estimated_dividend({"type": "DIVIDEND", "ticker": "X.L", "comments": "booked"})
    assert not is_estimated_dividend({"type": "BUY", "reason": "Automated dividend import"})


def test_cutoff_is_the_latest_ticker_less_booked_dividend():
    rows = [
        {**SWEEP, "date": "2026-07-10"},
        SWEEP,
        _estimate("2026-09-01"),
        {"type": "DEPOSIT", "date": "2026-09-30", "amount_minor": 100},
    ]
    assert booked_income_cutoff(rows) == "2026-08-10"
    assert booked_income_cutoff([_estimate("2026-07-16")]) is None


def test_marks_only_estimates_on_or_before_the_cutoff_and_is_idempotent():
    rows = [SWEEP, _estimate("2026-07-16"), _estimate("2026-08-10"), _estimate("2026-08-13", "UKW.L")]

    assert mark_attribution_only(rows) == 2

    assert [is_attribution_only(r) for r in rows] == [False, True, True, False]
    assert ATTRIBUTION_ONLY_KEY not in rows[0]
    assert mark_attribution_only(rows) == 0


def test_a_later_booked_sweep_covers_estimates_that_were_still_income():
    rows = [SWEEP, _estimate("2026-08-13", "UKW.L")]
    mark_attribution_only(rows)
    assert not is_attribution_only(rows[1])

    rows.append({**SWEEP, "date": "2026-09-10", "amount_minor": 193501})

    assert mark_attribution_only(rows) == 1
    assert is_attribution_only(rows[1])


def test_flag_is_removed_when_no_booked_row_covers_the_estimate_any_more():
    rows = [_estimate("2026-07-16", attribution_only=True)]

    assert mark_attribution_only(rows) == 1
    assert ATTRIBUTION_ONLY_KEY not in rows[0]


def test_account_without_booked_sweeps_keeps_every_estimate_as_income():
    rows = [_estimate("2026-07-16"), _estimate("2026-08-13", "UKW.L")]

    assert mark_attribution_only(rows) == 0
    assert not any(is_attribution_only(r) for r in rows)


# ── readers skip attribution-only rows ──


def _rebuilt_cash(transactions: list[dict]) -> float:
    replay = holdings_rebuild.replay_transactions(transactions, warn=False)
    return replay.cash


def test_holdings_rebuild_counts_the_booked_sweep_once():
    covered = [SWEEP, _estimate("2026-07-16", attribution_only=True)]
    uncovered = [SWEEP, _estimate("2026-08-13", "UKW.L", amount_minor=30863)]

    assert _rebuilt_cash(covered) == pytest.approx(1608.15)
    assert _rebuilt_cash(uncovered) == pytest.approx(1608.15 + 308.63)


END = date(2026, 2, 27)
CLOSES = {"AAA.L": {"2026-01-29": 100.0, "2026-02-12": 99.0}}
LEDGER = [
    {"date": "2026-01-29", "type": "DEPOSIT", "amount_minor": 100000},
    {"date": "2026-01-29", "type": "BUY", "ticker": "AAA.L", "units": 10, "amount_minor": 100000},
    {"date": "2026-02-13", "type": "DIVIDEND", "amount_minor": 3000},
]


def _ledger_perf(transactions: list[dict], *, trade_cash: bool):
    def load(key, start, end):
        points = CLOSES.get(key, {})
        return pd.Series({pd.Timestamp(day): price for day, price in points.items()}, dtype=float)

    ledger = lp.AccountLedger("isa", transactions, trade_cash)
    return lp.build_ledger_performance([ledger], END, price_loader=load)


@pytest.mark.parametrize("trade_cash", [True, False])
def test_ledger_performance_ignores_attribution_only_rows(trade_cash):
    baseline = _ledger_perf(copy.deepcopy(LEDGER), trade_cash=trade_cash)
    covered_estimate = _estimate("2026-02-12", "AAA.L", amount_minor=3100, attribution_only=True)
    with_estimate = _ledger_perf([*copy.deepcopy(LEDGER), covered_estimate], trade_cash=trade_cash)

    pd.testing.assert_series_equal(with_estimate.values, baseline.values)
    pd.testing.assert_series_equal(with_estimate.returns, baseline.returns)
    pd.testing.assert_frame_equal(with_estimate.instrument_pnl, baseline.instrument_pnl)


def test_position_returns_leave_estimates_to_the_full_history_estimate():
    rows = [
        {"date": "2026-01-29", "type": "BUY", "ticker": "AAA.L", "units": 10, "amount_minor": 100000},
        _estimate("2026-02-12", "AAA.L", amount_minor=3100),
        {"date": "2026-02-20", "type": "DIVIDEND", "ticker": "BBB.L", "amount_minor": 500},
    ]

    returns = position_returns(rows, as_of=END)

    # No recorded income row is left for AAA.L, so attach_total_returns falls
    # back to the full-history estimate for it.
    assert "AAA.L" not in returns
    assert returns["BBB.L"].income_gbp == pytest.approx(5.0)
