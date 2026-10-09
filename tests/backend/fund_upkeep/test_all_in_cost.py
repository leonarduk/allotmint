"""All-in annual cost: fund charges plus 12 months of fees (#10482). Synthetic data only."""

from datetime import date

import pytest

from backend.fund_upkeep.all_in_cost import compute_all_in_cost

TODAY = date(2026, 10, 9)

PORTFOLIO = {
    "accounts": [
        {
            "account_type": "ISA",
            "holdings": [
                {"ticker": "FUNDA.L", "market_value_gbp": 10_000.0, "ongoing_charge_pct": 0.20},
                {"ticker": "FUNDB.L", "market_value_gbp": 5_000.0, "ongoing_charge_pct": 0.80},
                {"ticker": "NOFEE.L", "market_value_gbp": 4_000.0, "ongoing_charge_pct": None},
                {"ticker": "CASH.GBP", "market_value_gbp": 1_000.0, "instrument_type": "cash"},
            ],
        },
        {
            "account_type": "SIPP",
            "holdings": [{"ticker": "FUNDA.L", "market_value_gbp": 20_000.0, "ongoing_charge_pct": 0.20}],
        },
    ]
}

TRANSACTIONS = [
    # ISA: two trades with dealing fees, one without fee data, one platform fee and a refund.
    {"account": "isa", "type": "BUY", "date": "2026-03-01", "fees": 9.95},
    {"account": "isa", "type": "SELL", "date": "2026-06-01", "fees": 5.00},
    {"account": "isa", "type": "BUY", "date": "2026-07-01"},
    {"account": "isa", "type": "FEES", "date": "2026-09-30", "amount_minor": -2500},
    {"account": "isa", "type": "FEES_REFUND", "date": "2026-09-30", "amount_minor": 500},
    # Outside the 12-month window: ignored.
    {"account": "isa", "type": "BUY", "date": "2025-10-08", "fees": 100.0},
    # Not a cost.
    {"account": "isa", "type": "DIVIDEND", "date": "2026-05-01", "amount_minor": 12345},
    # SIPP platform fee.
    {"account": "sipp", "type": "FEES", "date": "2026-01-15", "amount_minor": 6000},
]


def _row(result, account):
    return next(r for r in result["accounts"] if r["account"] == account)


def test_hand_worked_fixture():
    result = compute_all_in_cost(PORTFOLIO, TRANSACTIONS, today=TODAY)

    isa = _row(result, "ISA")
    # OCF: 10,000 x 0.20% + 5,000 x 0.80% = 20 + 40.
    assert isa["fund_charges_gbp"] == 60.0
    assert isa["dealing_fees_gbp"] == 14.95
    assert isa["account_charges_gbp"] == 20.0  # 25.00 fee - 5.00 refund
    assert isa["known_cost_gbp"] == 94.95
    assert isa["value_gbp"] == 20_000.0
    assert isa["known_cost_pct"] == pytest.approx(94.95 / 20_000 * 100, abs=1e-4)
    # Unknowns are kept apart, never counted as zero cost.
    assert isa["unknown_value_gbp"] == 4_000.0
    assert isa["unknown_count"] == 1
    assert isa["trades_without_fee_data"] == 1
    assert isa["complete"] is False

    sipp = _row(result, "SIPP")
    assert sipp["fund_charges_gbp"] == 40.0
    assert sipp["account_charges_gbp"] == 60.0
    assert sipp["complete"] is True

    total = result["total"]
    assert total["known_cost_gbp"] == 194.95
    assert total["value_gbp"] == 40_000.0
    assert total["unknown_value_gbp"] == 4_000.0
    assert result["window"] == {"start": "2025-10-09", "end": "2026-10-09"}


def test_no_known_charge_is_unknown_not_zero():
    portfolio = {"accounts": [{"account_type": "GIA", "holdings": [{"ticker": "X.L", "market_value_gbp": 100.0}]}]}

    result = compute_all_in_cost(portfolio, [], today=TODAY)

    assert result["total"]["fund_charges_gbp"] is None
    assert result["total"]["unknown_value_gbp"] == 100.0
    assert result["total"]["complete"] is False


def test_costs_of_an_account_no_longer_held_still_count():
    result = compute_all_in_cost(
        {"accounts": []}, [{"account": "old", "type": "FEES", "date": "2026-02-01", "amount_minor": 1000}], today=TODAY
    )

    assert _row(result, "old")["account_charges_gbp"] == 10.0
    # No funds held: nothing is unknown, so the fund charge is a real 0.
    assert _row(result, "old")["fund_charges_gbp"] == 0.0
    assert result["total"]["complete"] is True
    assert result["total"]["known_cost_pct"] is None


def test_group_portfolio_matches_transactions_by_owner():
    portfolio = {
        "accounts": [
            {"owner": "alex", "account_type": "ISA", "holdings": []},
            {"owner": "sam", "account_type": "ISA", "holdings": []},
        ]
    }
    txs = [
        {"owner": "Alex", "account": "isa", "type": "FEES", "date": "2026-02-01", "amount_minor": 1000},
        {"owner": "sam", "account": "isa", "type": "FEES", "date": "2026-02-01", "amount_minor": 300},
    ]

    result = compute_all_in_cost(portfolio, txs, today=TODAY)

    by_owner = {r["owner"]: r["account_charges_gbp"] for r in result["accounts"]}
    assert by_owner == {"alex": 10.0, "sam": 3.0}


def test_zero_fee_is_known_and_missing_fee_is_unknown():
    txs = [
        {"account": "isa", "type": "BUY", "date": "2026-03-01", "fees": 0},
        {"account": "isa", "type": "BUY", "date": "2026-03-02", "fees": None},
    ]

    total = compute_all_in_cost({"accounts": []}, txs, today=TODAY)["total"]

    assert total["trade_count"] == 2
    assert total["dealing_fees_gbp"] == 0.0
    assert total["trades_without_fee_data"] == 1
