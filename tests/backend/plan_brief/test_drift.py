"""Deterministic facts of the plan-drift brief (#10475)."""

from __future__ import annotations

import json
from datetime import date

from backend.common.allocation_policy import AllocationPolicy
from backend.common.investment_plan import InvestmentPlan
from backend.plan_brief import drift
from tests.backend.plan_brief.conftest import PLAN_DATA, TODAY, portfolio


def _rows(table):
    return {row["class"]: row for row in table["rows"]}


def test_equity_six_points_over_target_in_pp_and_gbp(plan):
    table = drift.drift_table(plan, portfolio(), AllocationPolicy(tolerance_pct=5.0))

    rows = _rows(table)
    assert table["basis"] == "plan"
    assert table["total_value_gbp"] == 100_000.0
    assert rows["equity"]["drift_pp"] == 6.0
    assert rows["equity"]["drift_gbp"] == 6_000.0
    assert rows["equity"]["status"] == "over"
    assert rows["long_gilts"]["drift_pp"] == -10.0
    assert rows["long_gilts"]["drift_gbp"] == -10_000.0
    assert rows["long_gilts"]["status"] == "under"
    # Cash has no plan weight: 4pp over a 0% target, inside the 5pp band.
    assert rows["cash"]["status"] == "in_band"
    assert table["out_of_band"] == ["equity", "long_gilts"]


def test_tolerance_comes_from_the_allocation_policy(plan):
    table = drift.drift_table(plan, portfolio(), AllocationPolicy(tolerance_pct=7.0))
    assert _rows(table)["equity"]["status"] == "in_band"
    assert table["tolerance_pct"] == 7.0


def test_plan_vs_rebalance_targets_disagreement_is_its_own_line(plan):
    matching = AllocationPolicy(targets={"equity": 60.0, "long_gilts": 40.0})
    differing = AllocationPolicy(targets={"equity": 70.0, "bond": 30.0})
    assert drift.drift_table(plan, portfolio(), matching)["rebalance_targets_match"] is True
    assert drift.drift_table(plan, portfolio(), differing)["rebalance_targets_match"] is False
    assert drift.drift_table(plan, portfolio(), AllocationPolicy())["rebalance_targets_match"] is None


def test_uninvested_cash_dates_money_since_the_last_purchase():
    txs = [
        {"account": "ISA", "date": "2026-08-01", "type": "DEPOSIT", "amount_minor": 100000},
        {"account": "ISA", "date": "2026-08-02", "type": "BUY", "amount_minor": 100000, "ticker": "VWRL.L"},
        {"account": "ISA", "date": "2026-09-18", "type": "DEPOSIT", "amount_minor": 400000},
        {"account": "ISA", "date": "2026-09-25", "type": "TRANSFER_IN", "ticker": "X.L", "units": 1},
        {"account": "SIPP", "date": "2026-09-01", "type": "DEPOSIT", "amount_minor": 999900},
    ]
    [row] = drift.uninvested_cash(portfolio(), txs, TODAY)
    assert row["account"] == "ISA"
    assert row["cash_gbp"] == 4_000.0
    assert row["last_purchase"] == "2026-08-02"
    assert row["uninvested_since"] == "2026-09-18"
    assert row["days_uninvested"] == 21
    # amount_minor is pence.
    assert row["last_deposit_gbp"] == 4_000.0


def test_uninvested_cash_without_new_money_has_no_age():
    txs = [{"account": "isa", "date": "2026-10-01", "type": "BUY", "amount_minor": 5}]
    [row] = drift.uninvested_cash(portfolio(), txs, TODAY)
    assert row["uninvested_since"] is None and row["days_uninvested"] is None


def test_stale_evidence_and_review_due(plan):
    stale = drift.stale_evidence(plan, TODAY)
    assert [item["metric"] for item in stale] == ["gilt_20y_yield"]
    assert stale[0]["age_days"] == (TODAY - date(2025, 11, 1)).days

    review = drift.review_status(plan, TODAY)
    assert review == {
        "next_review": "2026-10-01",
        "due": True,
        "days_overdue": 8,
        "open_questions": ["Add index-linked gilts?"],
    }


def test_review_not_due_when_date_is_ahead():
    plan = InvestmentPlan.model_validate({**PLAN_DATA, "review": {"next_review": "2027-01-01"}})
    assert drift.review_status(plan, TODAY)["due"] is False


def test_changes_since_last_brief_in_gbp_and_big_movers():
    txs = [
        {"account": "ISA", "date": "2026-09-01", "type": "DEPOSIT", "amount_minor": 50000},  # before window
        {"account": "ISA", "date": "2026-09-20", "type": "DEPOSIT", "amount_minor": 400000},
        {"account": "ISA", "date": "2026-09-21", "type": "WITHDRAWAL", "amount_minor": -10000},
        {"account": "ISA", "date": "2026-09-22", "type": "BUY", "amount_minor": 250000},
        {"account": "ISA", "date": "2026-09-23", "type": "SELL", "amount_minor": 12345, "currency": "USD"},
        # A trade recorded without amount_minor: units * price_gbp (pounds per unit).
        {"account": "ISA", "date": "2026-09-24", "type": "BUY", "units": 10, "price_gbp": 9.5, "ticker": "IGLT.L"},
    ]
    previous = {
        "as_of": "2026-09-09",
        "drift": {"total_value_gbp": 90_000.0},
        "holdings_snapshot": {
            "VWRL.L": {"units": 100.0, "value_gbp": 55_000.0},
            "GLTL.L": {"units": 100.0, "value_gbp": 29_500.0},
        },
    }
    snapshot = drift.holdings_snapshot(portfolio())
    changes = drift.changes_since(txs, date(2026, 9, 9), TODAY, snapshot, previous)

    assert changes["contributions_gbp"] == 4_000.0
    assert changes["withdrawals_gbp"] == 100.0
    assert changes["purchases_gbp"] == 2_595.0
    assert changes["counts"]["purchases"] == 2
    assert changes["sales_gbp"] == 0.0
    assert changes["skipped_no_gbp_amount"] == 1
    assert changes["previous_total_value_gbp"] == 90_000.0
    # VWRL 550 -> 660 per unit (+20%); GLTL 295 -> 300 (+1.7%) is not a big mover.
    assert changes["big_movers"] == [{"ticker": "VWRL.L", "change_pct": 20.0, "value_gbp": 66_000.0}]


def test_build_facts_uses_previous_brief_date_for_changes(plan):
    facts = drift.build_facts(plan, portfolio(), AllocationPolicy(), [], TODAY, {"as_of": "2026-09-09"})
    assert facts["changes"]["since"] == "2026-09-09"
    facts = drift.build_facts(plan, portfolio(), AllocationPolicy(), [], TODAY, None)
    assert facts["changes"]["since"] == "2026-09-08"
    assert set(facts) == {"drift", "cash", "stale_evidence", "review", "changes", "holdings_snapshot"}


def test_load_owner_transactions_is_read_only(tmp_path):
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    (owner_dir / "ISA_transactions.json").write_text(
        json.dumps({"account_type": "ISA", "transactions": [{"date": "2026-01-01", "type": "DEPOSIT"}]})
    )
    (owner_dir / "bad_transactions.json").write_text("{not json")
    before = sorted(p.name for p in owner_dir.iterdir())

    rows = drift.load_owner_transactions(tmp_path, "alex")

    assert rows == [{"date": "2026-01-01", "type": "DEPOSIT", "account": "ISA"}]
    assert sorted(p.name for p in owner_dir.iterdir()) == before
