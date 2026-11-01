"""Structured cash ``kind`` rules (#10797): classify only the unambiguous rows."""

from __future__ import annotations

import pytest

from backend.common.cash_kind import CASH_KINDS, classify_cash_kind, is_isa_account, is_pension_account


def _row(tx_type, comments=None, amount_minor=10_000, ticker=None):
    return {"type": tx_type, "comments": comments, "amount_minor": amount_minor, "ticker": ticker}


@pytest.mark.parametrize(
    "tx_type,expected",
    [("WITHDRAWAL", "withdrawal"), ("withdrawal", "withdrawal"), ("INTEREST", "interest"), ("FEES", "fee"),
     ("FEE", "fee"), ("DIVIDEND", None), ("BUY", None), ("TRANSFER_OUT", None), (None, None)],
)  # fmt: skip
def test_kind_from_type_alone(tx_type, expected):
    assert classify_cash_kind(_row(tx_type), "gia") == expected


def test_cash_transfer_in_by_account_and_in_specie_left_alone():
    assert classify_cash_kind(_row("TRANSFER_IN"), "isa") == "isa_transfer_in"
    assert classify_cash_kind(_row("TRANSFER_IN"), "sipp") == "transfer_in"
    assert classify_cash_kind(_row("TRANSFER_IN", ticker="VWRL.L"), "sipp") is None


def test_cash_transfer_in_with_ticker_on_isa_is_left_alone():
    # An in-specie transfer into an ISA is not a cash ISA transfer (#11193).
    assert classify_cash_kind(_row("TRANSFER_IN", ticker="VWRL.L"), "isa") is None


@pytest.mark.parametrize(
    "comments,amount,expected",
    [
        (None, 10_000, "isa_subscription"),
        ("Monthly subscription", 10_000, "isa_subscription"),
        ("Debit card payment", -3_000, "isa_subscription"),
        ("ISA transfer in from another provider", 10_000, "isa_transfer_in"),
        ("Transferred in from Example ISA", 10_000, "isa_transfer_in"),
        ("Transfer from bank", 10_000, None),
        ("Refund", 10_000, None),
        ("Reversal", -10_000, None),
        ("Government bonus", 10_000, None),
        ("Interest", 10_000, None),
    ],
)
def test_isa_deposits(comments, amount, expected):
    assert classify_cash_kind(_row("DEPOSIT", comments, amount), "isa") == expected


@pytest.mark.parametrize(
    "comments,expected",
    [
        ("Personal contribution", "personal_contribution"),
        ("SIPP contribution", "personal_contribution"),
        ("Tax relief", "tax_relief"),
        ("Tax relief on contribution", "tax_relief"),
        ("Relief at source top-up", "tax_relief"),
        ("Employer contribution", "employer_contribution"),
        ("Salary sacrifice contribution", "employer_contribution"),
        ("Transfer in from Example Pension", "transfer_in"),
        ("Transferred in", "transfer_in"),
        # The #737 risk: these must never become contributions or transfers by guesswork.
        ("Transfer of contribution", None),
        ("Transfer in of employer contributions", None),
        ("Transfer from cash account", None),
        ("Employer tax relief", None),
        ("Contribution refund", None),
        ("Contribution reversal", None),
        ("Correction", None),
        ("Employers", None),
        (None, None),
        ("Payment", None),
    ],
)
def test_pension_deposits(comments, expected):
    assert classify_cash_kind(_row("DEPOSIT", comments), "sipp") == expected


def test_negative_or_missing_pension_amount_is_left_unclassified():
    assert classify_cash_kind(_row("DEPOSIT", "Personal contribution", -10_000), "sipp") is None
    assert classify_cash_kind(_row("DEPOSIT", "Personal contribution", None), "sipp") is None


def test_deposits_into_other_accounts_are_left_unclassified():
    assert classify_cash_kind(_row("DEPOSIT", "Personal contribution"), "gia") is None
    assert classify_cash_kind(_row("DEPOSIT", "Transfer in"), "savings") is None


def test_vocabulary_matches_the_issue():
    assert CASH_KINDS == {
        "personal_contribution",
        "tax_relief",
        "employer_contribution",
        "transfer_in",
        "isa_subscription",
        "isa_transfer_in",
        "withdrawal",
        "interest",
        "fee",
    }


def test_account_detection():
    assert is_isa_account("ISA") and is_isa_account("lisa") and not is_isa_account("sipp")
    assert is_pension_account("SIPP") and is_pension_account("kz:sipp") and not is_pension_account("isa")
