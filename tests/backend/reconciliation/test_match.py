"""Deterministic statement-vs-ledger matching (#10474). No LLM: extractions are built by hand."""

from __future__ import annotations

from backend.reconciliation.extract import normalise_statement
from backend.reconciliation.match import RECONCILIATION_REASON, reconcile
from backend.reconciliation.models import RawStatement

# A synthetic quarter: a deposit, one BUY with an £11.95 fee, monthly interest.
STATEMENT = {
    "document_type": "statement",
    "period_start": "2026-01-01",
    "period_end": "2026-03-31",
    "opening_cash": 0,
    "closing_cash": 3990.55,
    "rows": [
        {"date": "2026-01-05", "type": "DEPOSIT", "description": "Debit card", "amount": 5000},
        {
            "date": "2026-01-10",
            "type": "BUY",
            "description": "BP PLC",
            "ticker": "BP.L",
            "units": 200,
            "price": 500,
            "price_unit": "GBX",
            "consideration": 1000,
            "fees": 11.95,
            "amount": 1011.95,
        },
        {"date": "2026-03-31", "type": "INTEREST", "description": "Interest", "amount": 2.50},
    ],
}

DEPOSIT = {"id": "alice:isa:0", "date": "2026-01-05", "type": "DEPOSIT", "amount_minor": 500_000}
BUY_NO_FEE = {
    "id": "alice:isa:1",
    "date": "2026-01-10",
    "type": "BUY",
    "ticker": "BP.L",
    "units": 200,
    "price_gbp": 5.0,
    "fees": 0,
    "reason": "Income",
}


def _extraction(**overrides):
    return normalise_statement(RawStatement.model_validate({**STATEMENT, **overrides}))


def _reconcile(extraction, ledger, **kwargs):
    return reconcile(extraction, ledger, owner="alice", account="isa", **kwargs)


def test_missing_interest_and_wrong_fee_are_exactly_the_two_diffs():
    extraction = _extraction(closing_cash=None)

    matched, diffs, warnings = _reconcile(extraction, [DEPOSIT, BUY_NO_FEE])

    assert [m.ledger_id for m in matched] == ["alice:isa:0"]
    assert sorted(d.kind for d in diffs) == ["fee_mismatch", "missing_from_ledger"]
    fee = next(d for d in diffs if d.kind == "fee_mismatch")
    assert fee.ledger_id == "alice:isa:1"
    assert (fee.ledger_minor, fee.statement_minor, fee.difference_minor) == (0, 1195, 1195)
    assert "fee recorded as £0.00, statement says £11.95" in fee.message
    assert fee.suggestion.request.method == "PUT"
    assert fee.suggestion.request.path == "/transactions/alice:isa:1"
    assert fee.suggestion.request.body["fees"] == 11.95
    assert fee.suggestion.request.body["units"] == 200

    interest = next(d for d in diffs if d.kind == "missing_from_ledger")
    assert interest.statement_minor == 250
    assert interest.suggestion.request.method == "POST"
    assert interest.suggestion.request.path == "/transactions"
    assert interest.suggestion.request.body == {
        "owner": "alice",
        "account": "isa",
        "date": "2026-03-31",
        "type": "INTEREST",
        "amount_minor": 250,
        "reason": RECONCILIATION_REASON,
        "comments": "From broker statement: Interest",
    }
    assert warnings == []


def test_fully_reconciled_ledger_has_no_diffs():
    ledger = [
        DEPOSIT,
        {**BUY_NO_FEE, "fees": 11.95},
        {"id": "alice:isa:2", "date": "2026-03-31", "type": "INTEREST", "amount_minor": 250},
    ]

    matched, diffs, _ = _reconcile(_extraction(), ledger, trade_cash=True)

    assert diffs == []
    assert len(matched) == 3


def test_closing_cash_difference_is_reported_in_pounds_from_pence():
    # Ledger has the deposit and BUY (with fee) but no interest: cash is £2.50 short.
    ledger = [DEPOSIT, {**BUY_NO_FEE, "fees": 11.95}]

    _, diffs, _ = _reconcile(_extraction(), ledger, trade_cash=True)

    cash = next(d for d in diffs if d.kind == "cash_mismatch")
    assert cash.statement_minor == 399_055
    assert cash.ledger_minor == 398_805
    assert cash.difference_minor == 250
    assert "£3,990.55" in cash.message and "£3,988.05" in cash.message and "£2.50" in cash.message


def test_ledger_without_cash_movements_warns_instead_of_comparing():
    _, diffs, warnings = _reconcile(_extraction(), [{**BUY_NO_FEE, "fees": 11.95}])

    assert not any(d.kind == "cash_mismatch" for d in diffs)
    assert any("no cash movements" in w for w in warnings)


def test_settlement_date_within_tolerance_still_matches():
    ledger = [DEPOSIT, {**BUY_NO_FEE, "date": "2026-01-12", "fees": 11.95}]

    matched, diffs, _ = _reconcile(_extraction(closing_cash=None, rows=STATEMENT["rows"][:2]), ledger)

    assert {m.ledger_id for m in matched} == {"alice:isa:0", "alice:isa:1"}
    assert diffs == []


def test_outside_tolerance_is_missing_on_both_sides():
    ledger = [DEPOSIT, {**BUY_NO_FEE, "date": "2026-01-20", "fees": 11.95}]

    _, diffs, _ = _reconcile(_extraction(closing_cash=None, rows=STATEMENT["rows"][:2]), ledger)

    assert sorted(d.kind for d in diffs) == ["missing_from_ledger", "missing_from_statement"]


def test_exact_match_is_not_stolen_by_an_earlier_near_miss():
    rows = [
        {"date": "2026-02-01", "type": "INTEREST", "amount": 3.00},
        {"date": "2026-02-02", "type": "INTEREST", "amount": 2.00},
    ]
    ledger = [{"id": "alice:isa:0", "date": "2026-02-02", "type": "INTEREST", "amount_minor": 300}]

    matched, diffs, _ = _reconcile(_extraction(rows=rows, closing_cash=None), ledger)

    assert [(m.statement_index, m.ledger_id) for m in matched] == [(0, "alice:isa:0")]
    assert [(d.kind, d.statement_index) for d in diffs] == [("missing_from_ledger", 1)]


def test_isin_resolves_to_ledger_ticker():
    rows = [
        {
            "date": "2026-01-10",
            "type": "BUY",
            "isin": "gb0007980591",
            "units": 200,
            "price": 5,
            "consideration": 1000,
            "fees": 11.95,
        }
    ]
    ledger = [{**BUY_NO_FEE, "fees": 11.95}]

    matched, diffs, _ = _reconcile(
        _extraction(rows=rows, closing_cash=None), ledger, isin_to_ticker={"GB0007980591": "BP.L"}
    )

    assert diffs == [] and len(matched) == 1


def test_different_ticker_does_not_match():
    ledger = [DEPOSIT, {**BUY_NO_FEE, "ticker": "SHEL.L", "fees": 11.95}]

    _, diffs, _ = _reconcile(_extraction(closing_cash=None, rows=STATEMENT["rows"][:2]), ledger)

    assert sorted(d.kind for d in diffs) == ["missing_from_ledger", "missing_from_statement"]


def test_amount_mismatch_when_price_differs():
    ledger = [{**BUY_NO_FEE, "price_gbp": 5.5, "fees": 11.95}]

    _, diffs, _ = _reconcile(_extraction(closing_cash=None, rows=STATEMENT["rows"][1:2]), ledger)

    assert [d.kind for d in diffs] == ["amount_mismatch"]
    assert diffs[0].difference_minor == -10_000
    assert diffs[0].suggestion.request is None


def test_contract_note_does_not_report_other_ledger_rows():
    extraction = _extraction(document_type="contract_note", closing_cash=None, rows=STATEMENT["rows"][1:2])
    ledger = [DEPOSIT, {**BUY_NO_FEE, "fees": 11.95}]

    matched, diffs, _ = _reconcile(extraction, ledger)

    assert diffs == [] and len(matched) == 1


def test_missing_trade_suggests_create_with_pounds_price():
    _, diffs, _ = _reconcile(_extraction(closing_cash=None, rows=STATEMENT["rows"][1:2]), [])

    body = diffs[0].suggestion.request.body
    assert body["type"] == "BUY"
    assert body["ticker"] == "BP.L"
    assert body["price_gbp"] == 5.0  # 500p normalised to pounds
    assert body["units"] == 200
    assert body["fees"] == 11.95


def test_trade_without_instrument_has_no_automatic_request():
    rows = [
        {"date": "2026-01-10", "type": "BUY", "description": "Unknown fund", "units": 1, "price": 1, "consideration": 1}
    ]

    _, diffs, _ = _reconcile(_extraction(rows=rows, closing_cash=None), [])

    assert diffs[0].kind == "missing_from_ledger"
    assert diffs[0].suggestion.request is None


def test_closing_units_difference_is_reported():
    holdings = [{"ticker": "BP.L", "units": 250}, {"isin": "GB00B03MLX29", "name": "Shell", "units": 10}]

    _, diffs, warnings = _reconcile(
        _extraction(closing_cash=None, rows=STATEMENT["rows"][1:2], closing_holdings=holdings),
        [{**BUY_NO_FEE, "fees": 11.95}],
    )

    units = [d for d in diffs if d.kind == "units_mismatch"]
    assert [(d.ticker, d.statement_units, d.ledger_units) for d in units] == [("BP.L", 250, 200)]
    assert any("Shell" in w for w in warnings)


def test_ledger_rows_after_period_end_are_ignored_for_closing_balances():
    later = {"id": "alice:isa:9", "date": "2026-04-02", "type": "DEPOSIT", "amount_minor": 100_000}
    ledger = [
        DEPOSIT,
        {**BUY_NO_FEE, "fees": 11.95},
        {"id": "alice:isa:2", "date": "2026-03-31", "type": "INTEREST", "amount_minor": 250},
        later,
    ]

    _, diffs, _ = _reconcile(_extraction(), ledger, trade_cash=True)

    assert diffs == []


def test_matching_is_deterministic():
    extraction = _extraction()
    ledger = [DEPOSIT, BUY_NO_FEE]

    first = _reconcile(extraction, ledger, trade_cash=True)
    second = _reconcile(extraction, list(ledger), trade_cash=True)

    assert first == second
    assert [d.date for d in first[1]] == sorted(d.date for d in first[1])
