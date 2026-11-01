"""Contribution-schedule and all-in-fee defaults for the readiness monitor (#10510). Synthetic data only."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from backend.allowance_guardian.schedule import ContributionSchedule, ScheduledContribution, save_schedule
from backend.common import portfolio as portfolio_mod
from backend.retirement import defaults

ON = dt.date(2030, 1, 15)


def _item(account="SIPP", amount=10_000, source="personal_relief_at_source", **extra) -> ScheduledContribution:
    return ScheduledContribution(
        account=account, amount_minor=amount, source=source, expected_day=1, start_date="2029-01-01", **extra
    )


def test_schedule_annual_total_counts_current_dc_pension_entries_only():
    items = [
        _item(),  # £100/month net -> £125 gross -> £1,500 a year
        _item(amount=30_000, source="employer", frequency="quarterly"),  # £1,200 a year
        _item(account="ISA", amount=50_000, source="isa_subscription"),  # not a pension
        _item(account="workplace", source="employer"),  # not in the forecast's DC pot
        _item(end_date="2029-12-31"),  # ended
        ScheduledContribution(
            account="SIPP", amount_minor=99_999, source="employer", expected_day=1, start_date="2030-02-01"
        ),  # not started
    ]
    assert defaults.schedule_annual_gbp(items, ON) == (2700.0, 2)


def test_scheduled_contribution_reads_the_saved_schedule(tmp_path):
    save_schedule(ContributionSchedule(owner="alex", contributions=[_item(source="employer")]), tmp_path)
    found = defaults.scheduled_contribution("alex", tmp_path, ON)
    assert (found.value, found.source) == (1200.0, "schedule")
    assert "£1,200.00" in found.notes[0] and "1 current DC pension entry" in found.notes[0]


def test_no_schedule_means_no_default(tmp_path):
    found = defaults.scheduled_contribution("alex", tmp_path, ON)
    assert (found.value, found.source, found.notes) == (None, None, [])


def test_unreadable_schedule_is_noted_not_raised(tmp_path, caplog):
    path = tmp_path / "contribution_schedules" / "alex.json"
    path.parent.mkdir()
    path.write_text('{"owner": "alex", "contributions": [{"account": "SIPP"}]}')
    with caplog.at_level("WARNING"):
        found = defaults.scheduled_contribution("alex", tmp_path, ON)
    assert found.value is None
    assert "could not be read" in found.notes[0]
    assert "Contribution schedule unreadable" in caplog.text


def _row(account, value, cost, complete=True):
    return {"account": account, "value_gbp": value, "known_cost_gbp": cost, "complete": complete}


def test_dc_fee_pct_uses_pension_accounts_only():
    found = defaults.dc_fee_pct({"accounts": [_row("sipp", 100_000.0, 500.0), _row("isa", 50_000.0, 1_000.0)]})
    assert (found.value, found.source, found.notes) == (0.5, "all_in_cost", [])


def test_incomplete_costs_are_a_lower_bound():
    found = defaults.dc_fee_pct({"accounts": [_row("SIPP", 100_000.0, 250.0, complete=False)]})
    assert found.value == 0.25
    assert "lower bound" in found.notes[0]


@pytest.mark.parametrize(
    "rows",
    [[_row("sipp", 100_000.0, 0.0, complete=False)], [_row("isa", 100_000.0, 500.0)], []],
    ids=["unknown-charges", "no-pension-account", "no-accounts"],
)
def test_no_usable_fee_is_not_applied(rows):
    assert defaults.dc_fee_pct({"accounts": rows}).value is None


def test_pension_fee_from_portfolio_and_last_years_fees(monkeypatch, tmp_path):
    portfolio = {
        "accounts": [
            {
                "account_type": "sipp",
                "holdings": [{"ticker": "FUND.L", "market_value_gbp": 100_000.0, "ongoing_charge_pct": 0.2}],
            },
            {
                "account_type": "isa",
                "holdings": [{"ticker": "OTHER.L", "market_value_gbp": 10_000.0, "ongoing_charge_pct": 1.0}],
            },
        ]
    }
    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", lambda owner, root: portfolio)
    transactions = [
        SimpleNamespace(owner="alex", account="sipp", type="FEES", date="2029-06-01", amount_minor=10_000),
        SimpleNamespace(owner="sam", account="sipp", type="FEES", date="2029-06-01", amount_minor=99_999),
        {"owner": "alex", "account": "sipp", "type": "FEES", "date": "2028-01-01", "amount_minor": 99_999},
    ]
    found = defaults.pension_fee("alex", tmp_path, lambda: transactions, ON)
    # £200 fund charges + £100 account charges in the last 12 months on £100,000.
    assert (found.value, found.source) == (0.3, "all_in_cost")


def test_pension_fee_without_a_portfolio_is_not_applied(monkeypatch, tmp_path):
    def missing(owner, root):
        raise FileNotFoundError(owner)

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", missing)
    assert defaults.pension_fee("alex", tmp_path, lambda: [], ON).value is None
