"""Expected-vs-actual contribution matching (#10479). Synthetic fixtures only."""

from __future__ import annotations

from datetime import date

import pytest

from backend.allowance_guardian.match import match_contributions
from backend.allowance_guardian.schedule import ScheduledContribution, expected_dates
from backend.routes.transactions import Transaction

TAX_YEAR_START = date(2026, 4, 6)
TODAY = date(2026, 10, 9)


def _tx(day: str, amount_minor: int, comments: str = "Employer contribution", account: str = "sipp", **extra):
    return Transaction(
        owner="alex",
        account=account,
        id=f"{account}-{day}-{amount_minor}-{len(comments)}",
        type="DEPOSIT",
        date=day,
        amount_minor=amount_minor,
        currency="GBP",
        comments=comments,
        **extra,
    )


def _item(**fields) -> ScheduledContribution:
    base = {
        "account": "sipp",
        "amount_minor": 50_000,
        "frequency": "monthly",
        "source": "employer",
        "expected_day": 28,
        "start_date": "2026-04-28",
    }
    return ScheduledContribution(**{**base, **fields})


def _statuses(result):
    return [(r["expected_date"], r["status"]) for r in result["results"]]


def test_each_status_is_classified():
    rows = [
        _tx("2026-04-28", 50_000),  # on time
        _tx("2026-05-31", 50_000),  # 3 days late
        # June: nothing at all
        _tx("2026-07-28", 45_000),  # short
        _tx("2026-08-27", 25_000),  # split payment...
        _tx("2026-08-28", 25_000),  # ...completing the amount
        # September: nothing yet, but the window is still open on 9 October
    ]
    result = match_contributions([_item()], rows, TAX_YEAR_START, TODAY)
    assert _statuses(result) == [
        ("2026-04-28", "on_time"),
        ("2026-05-28", "late"),
        ("2026-06-28", "missing"),
        ("2026-07-28", "wrong_amount"),
        ("2026-08-28", "on_time"),
        ("2026-09-28", "awaiting"),
    ]
    late = result["results"][1]
    assert late["days_late"] == 3
    wrong = result["results"][3]
    assert wrong["received_amount_minor"] == 45_000
    assert wrong["difference_minor"] == -5_000
    assert len(result["results"][4]["matched_rows"]) == 2
    assert result["counts"] == {"on_time": 2, "late": 1, "wrong_amount": 1, "missing": 1, "awaiting": 1}
    assert result["unmatched_deposits"] == []


def test_three_days_late_is_late_not_missing():
    result = match_contributions([_item()], [_tx("2026-06-01", 50_000)], TAX_YEAR_START, date(2026, 6, 20))
    by_date = dict(_statuses(result))
    assert by_date["2026-05-28"] == "late"


def test_no_row_within_window_is_missing_once_the_window_closes():
    item = _item(start_date="2026-09-01", expected_day=1)
    assert _statuses(match_contributions([item], [], TAX_YEAR_START, date(2026, 9, 10))) == [("2026-09-01", "awaiting")]
    assert _statuses(match_contributions([item], [], TAX_YEAR_START, date(2026, 9, 16))) == [("2026-09-01", "missing")]
    # A payment long after the window does not rescue it.
    late_row = [_tx("2026-09-25", 50_000)]
    assert _statuses(match_contributions([item], late_row, TAX_YEAR_START, date(2026, 9, 26))) == [
        ("2026-09-01", "missing")
    ]


def test_partial_payment_waits_while_window_is_open():
    result = match_contributions([_item(start_date="2026-09-28")], [_tx("2026-09-28", 20_000)], TAX_YEAR_START, TODAY)
    assert _statuses(result) == [("2026-09-28", "awaiting")]


def test_personal_schedule_ignores_employer_rows_and_relief_top_ups():
    personal = _item(source="personal_relief_at_source", amount_minor=80_000, expected_day=1, start_date="2026-09-01")
    rows = [
        _tx("2026-09-01", 80_000, comments="SIPP contribution (debit card)"),
        _tx("2026-09-02", 80_000, comments="Employer contribution"),
        _tx("2026-10-05", 20_000, comments="SIPP tax relief claim (relief at source)"),
    ]
    result = match_contributions([personal], rows, TAX_YEAR_START, TODAY)
    assert _statuses(result) == [("2026-09-01", "on_time"), ("2026-10-01", "awaiting")]
    assert result["results"][0]["matched_rows"][0]["date"] == "2026-09-01"
    # The employer row is left over; the relief top-up is never a candidate.
    assert [row["date"] for row in result["unmatched_deposits"]] == ["2026-09-02"]


def test_each_row_is_used_once():
    # Two schedules expecting the same amount on the same day, one row arrived.
    first, second = _item(label="a", start_date="2026-09-28"), _item(label="b", start_date="2026-09-28")
    result = match_contributions([first, second], [_tx("2026-09-28", 50_000)], TAX_YEAR_START, date(2026, 10, 20))
    assert sorted(r["status"] for r in result["results"]) == ["missing", "on_time"]


def test_transfers_and_other_accounts_are_not_matched():
    rows = [
        _tx("2026-09-28", 50_000, comments="Employer scheme transfer in"),
        _tx("2026-09-28", 50_000, account="isa"),
    ]
    result = match_contributions([_item(start_date="2026-09-28")], rows, TAX_YEAR_START, date(2026, 10, 20))
    assert _statuses(result) == [("2026-09-28", "missing")]


@pytest.mark.parametrize(
    "comment", ["Refund of employer contribution", "Employer contribution reversal", "Employer scheme transfer"]
)
def test_refunds_reversals_and_transfers_are_never_matched(comment):
    rows = [_tx("2026-09-28", 50_000, comments=comment)]
    result = match_contributions([_item(start_date="2026-09-28")], rows, TAX_YEAR_START, date(2026, 10, 20))
    assert _statuses(result) == [("2026-09-28", "missing")]
    assert result["unmatched_deposits"] == []


def test_employer_tag_must_be_a_whole_word():
    personal = _item(source="personal_gross", start_date="2026-09-28")
    rows = [_tx("2026-09-28", 50_000, comments="Unemployerish contribution")]
    result = match_contributions([personal], rows, TAX_YEAR_START, date(2026, 10, 20))
    assert _statuses(result) == [("2026-09-28", "on_time")]


def test_isa_subscription_matches_isa_deposits():
    item = _item(account="isa", source="isa_subscription", expected_day=5, start_date="2026-09-05")
    rows = [_tx("2026-09-05", 50_000, comments="Regular subscription", account="isa")]
    result = match_contributions([item], rows, TAX_YEAR_START, TODAY)
    assert _statuses(result)[0] == ("2026-09-05", "on_time")


def test_expected_dates_clamp_to_short_months_and_respect_frequency():
    monthly = _item(expected_day=31, start_date="2027-01-31")
    assert [d.isoformat() for d in expected_dates(monthly, date(2027, 1, 1), date(2027, 4, 5))] == [
        "2027-01-31",
        "2027-02-28",
        "2027-03-31",
    ]
    quarterly = _item(frequency="quarterly", start_date="2026-05-28", end_date="2027-01-01")
    assert [d.isoformat() for d in expected_dates(quarterly, TAX_YEAR_START, date(2027, 4, 5))] == [
        "2026-05-28",
        "2026-08-28",
        "2026-11-28",
    ]


@pytest.mark.parametrize(
    "fields",
    [
        {"account": "isa", "source": "employer"},
        {"account": "sipp", "source": "isa_subscription"},
        {"end_date": "2026-01-01"},
        {"amount_minor": 0},
        {"expected_day": 32},
    ],
)
def test_invalid_schedule_items_are_rejected(fields):
    with pytest.raises(ValueError):
        _item(**fields)
