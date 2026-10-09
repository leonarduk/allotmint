"""Annual allowance projection with carry-forward (#10479). Synthetic, hand-worked figures."""

from __future__ import annotations

from datetime import date

import pytest

from backend.allowance_guardian.projection import (
    isa_subscribed_minor,
    project_isa_allowance,
    project_pension_allowance,
    tax_year_bounds,
)
from backend.allowance_guardian.schedule import ScheduledContribution
from backend.routes.transactions import Transaction

TODAY = date(2026, 10, 9)  # tax year 2026-2027


def _view(current_gross_gbp: float, unused_gbp: tuple[float, float, float], employer_gbp: float = 0.0) -> dict:
    """A carry_forward_view-shaped result for 2026-27 with three earlier years."""
    labels = ["2023-2024", "2024-2025", "2025-2026"]
    rows = [
        {"tax_year": label, "annual_allowance_gbp": 60_000.0, "unused_allowance_gbp": unused}
        | {"is_current_tax_year": False}
        for label, unused in zip(labels, unused_gbp)
    ]
    rows.append(
        {
            "tax_year": "2026-2027",
            "annual_allowance_gbp": 60_000.0,
            "annual_allowance_assumed": False,
            "gross_contributions_gbp": current_gross_gbp,
            "employer_contributions_gbp": employer_gbp,
            "excess_not_covered_by_carry_forward_gbp": 0.0,
            "unused_allowance_gbp": max(60_000.0 - current_gross_gbp, 0.0),
            "is_current_tax_year": True,
        }
    )
    return {
        "current_tax_year": "2026-2027",
        "tax_years": rows,
        "current_year_allowance_remaining_gbp": max(60_000.0 - current_gross_gbp, 0.0),
        "carry_forward_available_gbp": sum(unused_gbp),
    }


def _monthly(amount_minor: int, source: str = "employer", day: int = 28, account: str = "sipp"):
    return ScheduledContribution(
        account=account,
        amount_minor=amount_minor,
        source=source,
        expected_day=day,
        start_date=date(2026, 4, day),
    )


def test_breach_month_after_carry_forward_is_used_up():
    """Hand-worked example.

    2026-27 so far: 50,000 of the 60,000 allowance used, so 10,000 left. Unused in the
    three previous years: 20,000 (2023-24), 30,000 (2024-25), 40,000 (2025-26), so
    100,000 is available in all. 25,000 a month is scheduled on the 28th; six payments
    remain (Oct to Mar), 150,000 in all.

      28 Oct: 10,000 current year + 15,000 from 2023-24  -> carry-forward first needed
      28 Nov:  5,000 from 2023-24 + 20,000 from 2024-25
      28 Dec: 10,000 from 2024-25 + 15,000 from 2025-26
      28 Jan: 25,000 from 2025-26                         -> exactly 100,000 used, no excess
      28 Feb: 25,000 over                                 -> breach
      28 Mar: 25,000 over                                 -> 50,000 over by 5 April
    """
    view = _view(50_000.0, (20_000.0, 30_000.0, 40_000.0), employer_gbp=50_000.0)
    result = project_pension_allowance(view, [_monthly(2_500_000)], TODAY)

    assert result["used_to_date_minor"] == 5_000_000
    assert result["current_year_remaining_minor"] == 1_000_000
    assert result["carry_forward_available_minor"] == 9_000_000
    assert result["scheduled_remaining_minor"] == 15_000_000
    assert result["projected_total_minor"] == 20_000_000
    assert result["carry_forward_first_needed"] == {"date": "2026-10-28", "month": "2026-10"}
    assert result["projected_breach"] == {"date": "2027-02-28", "month": "2027-02"}
    assert result["projected_excess_minor"] == 5_000_000
    assert [row["projected_unused_minor"] for row in result["carry_forward_by_year"]] == [0, 0, 0]
    assert result["employer_contributions_to_date_minor"] == 5_000_000
    assert result["employer_category_supported"] is True

    timeline = {row["month"]: row for row in result["timeline"]}
    assert list(timeline) == ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03"]
    assert timeline["2026-11"]["carry_forward_remaining_minor"] == 5_000_000
    assert timeline["2027-01"]["projected_excess_minor"] == 0
    assert timeline["2027-02"]["projected_excess_minor"] == 2_500_000
    assert timeline["2027-03"]["projected_used_minor"] == 20_000_000


def test_carry_forward_uses_oldest_year_first():
    view = _view(55_000.0, (20_000.0, 30_000.0, 40_000.0))
    result = project_pension_allowance(view, [_monthly(1_000_000, day=15)], date(2027, 3, 1))
    # One payment left (15 March): 5,000 from the current year, then 5,000 from 2023-24.
    unused = [row["projected_unused_minor"] for row in result["carry_forward_by_year"]]
    assert unused == [1_500_000, 3_000_000, 4_000_000]
    assert result["projected_breach"] is None


def test_within_current_year_allowance_needs_no_carry_forward():
    result = project_pension_allowance(_view(10_000.0, (0.0, 0.0, 0.0)), [_monthly(100_000)], TODAY)
    assert result["carry_forward_first_needed"] is None
    assert result["projected_breach"] is None
    assert result["projected_excess_minor"] == 0


def test_relief_at_source_is_grossed_up_by_a_quarter():
    item = _monthly(80_000, source="personal_relief_at_source")
    result = project_pension_allowance(_view(0.0, (0.0, 0.0, 0.0)), [item], TODAY)
    assert result["scheduled_remaining_minor"] == 6 * 100_000


def test_isa_schedules_are_not_pension_contributions():
    isa = _monthly(100_000, source="isa_subscription", account="isa")
    result = project_pension_allowance(_view(0.0, (0.0, 0.0, 0.0)), [isa], TODAY)
    assert result["scheduled_remaining_minor"] == 0


def test_older_pro_without_employer_category_is_flagged():
    view = _view(0.0, (0.0, 0.0, 0.0))
    del view["tax_years"][-1]["employer_contributions_gbp"]
    assert project_pension_allowance(view, [], TODAY)["employer_category_supported"] is False


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 4, 5), (date(2025, 4, 6), date(2026, 4, 5))),
        (date(2026, 4, 6), (date(2026, 4, 6), date(2027, 4, 5))),
        (date(2027, 1, 1), (date(2026, 4, 6), date(2027, 4, 5))),
    ],
)
def test_tax_year_runs_6_april_to_5_april_not_calendar_year(day, expected):
    assert tax_year_bounds(day) == expected


def test_isa_projection_and_deadline():
    rows = [
        Transaction(owner="alex", account="isa", type="DEPOSIT", date="2026-05-01", amount_minor=1_000_000),
        Transaction(owner="alex", account="isa", type="DEPOSIT", date="2026-06-01", amount_minor=500_000,
                    comments="ISA transfer in from another provider"),
        Transaction(owner="alex", account="isa", type="DEPOSIT", date="2026-03-01", amount_minor=999_999),
    ]  # fmt: skip
    subscribed = isa_subscribed_minor(rows, TODAY)
    assert subscribed == 1_000_000
    item = _monthly(200_000, source="isa_subscription", account="isa", day=1)
    result = project_isa_allowance(subscribed, 2_000_000, [item], TODAY)
    # 1 Nov .. 1 Apr: six payments of 2,000 take 10,000 to 22,000, over the 20,000 on 1 April.
    assert result["scheduled_remaining_minor"] == 1_200_000
    assert result["projected_total_minor"] == 2_200_000
    assert result["projected_over_limit"] == {"date": "2027-04-01", "month": "2027-04"}
    assert result["deadline"] == "2027-04-05"
    assert result["days_to_deadline"] == 178


def test_projection_against_real_carry_forward_view():
    """The same arithmetic on allotmint-pro's carry_forward_view, when allotmint-pro is installed."""
    pension_tools = pytest.importorskip("allotmint_pro.mcp_server.pension_tools")
    rows = [
        Transaction(owner="alex", account="sipp", type="DEPOSIT", currency="GBP", date="2026-05-01",
                    amount_minor=4_000_000, comments="SIPP contribution"),
    ]  # fmt: skip
    view = pension_tools.carry_forward_view(rows, today=TODAY)
    # 20,000 left this year + 3 x 60,000 unused = 200,000; 50,000 a month from 15 Oct.
    result = project_pension_allowance(view, [_monthly(5_000_000, source="personal_gross", day=15)], TODAY)
    assert result["carry_forward_available_minor"] == 18_000_000
    assert result["carry_forward_first_needed"]["date"] == "2026-10-15"
    assert result["projected_breach"] == {"date": "2027-02-15", "month": "2027-02"}
