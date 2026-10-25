"""The allowance guardian on the Bots page (#10495). Synthetic owners and figures only."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from backend.allowance_guardian import report as guardian_report
from backend.allowance_guardian.bot import BOT_ID, AllowanceGuardianBot
from backend.allowance_guardian.schedule import ScheduledContribution
from backend.bots import registry
from backend.bots.registry import BotRunContext

TODAY = date(2026, 10, 9)
REAL_RUN = guardian_report.run


def _context(owner=None):
    started = datetime(2026, 10, 9, 9, tzinfo=timezone.utc)
    return BotRunContext(run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=started, owner=owner)


def _allowances() -> SimpleNamespace:
    """5,000 of this year's allowance left and no carry-forward (as the report tests)."""
    earlier = [
        {"tax_year": y, "annual_allowance_gbp": 60_000.0, "unused_allowance_gbp": 0.0, "is_current_tax_year": False}
        for y in ("2023-2024", "2024-2025", "2025-2026")
    ]
    current = {
        "tax_year": "2026-2027",
        "annual_allowance_gbp": 60_000.0,
        "gross_contributions_gbp": 55_000.0,
        "employer_contributions_gbp": 55_000.0,
        "excess_not_covered_by_carry_forward_gbp": 0.0,
        "is_current_tax_year": True,
    }
    view = {"tax_years": [*earlier, current], "current_year_allowance_remaining_gbp": 5_000.0}
    return SimpleNamespace(
        carry_forward_view=lambda transactions, today: view,
        annual_allowance_info=lambda account, tax_year: {"limit_gbp": 20_000.0, "assumed": False},
    )


def _schedule() -> list[ScheduledContribution]:
    return [
        ScheduledContribution(
            account="sipp", amount_minor=1_000_000, source="employer", expected_day=28, start_date="2026-04-28"
        ),
        ScheduledContribution(
            account="isa", amount_minor=500_000, source="isa_subscription", expected_day=1, start_date="2026-11-01"
        ),
    ]


def _synthetic_run(owner):
    return REAL_RUN(owner, today=TODAY, transactions=[], schedule=_schedule(), allowances=_allowances())


def test_registered_as_an_owner_scoped_rules_bot_without_a_schedule():
    bot = registry.get_bot(BOT_ID)

    assert isinstance(bot, AllowanceGuardianBot)
    assert (bot.kind, bot.scope) == ("rules", "owner")
    assert bot.default_schedule is None
    assert bot.settings_model.model_validate(bot.default_settings()).cadence == "monthly"


def test_projected_breach_is_summarised_with_its_month_and_no_amounts(monkeypatch):
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)

    result = AllowanceGuardianBot().run(_context("alex"), AllowanceGuardianBot.settings_model())

    assert result.status == "ok"
    [row] = result.report["owners"]
    assert row["owner"] == "alex" and row["schedule_count"] == 2
    assert row["breach_month"] == "2026-10"
    assert row["codes"]["pension_projected_breach"] == 1
    assert row["codes"]["contribution_missing"] == 1
    assert row["alerts"] == sum(row["codes"].values())
    assert "pension breach projected 2026-10" in result.summary
    assert result.summary.startswith(f"{row['alerts']} alerts ({row['critical']} critical) across 1 owner")
    # Alert messages carry amounts; the stored run report holds counts only.
    assert "£" not in json.dumps(result.report, ensure_ascii=False)


def test_one_owners_failure_does_not_stop_the_others(monkeypatch):
    plots = [SimpleNamespace(owner="alex"), SimpleNamespace(owner="sam")]
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: plots)

    def fake_run(owner):
        if owner == "sam":
            raise ValueError("schedule unreadable")
        return {"tax_year": "2026-2027", "schedule_count": 0, "alerts": [], "pension_allowance": {}}

    monkeypatch.setattr(guardian_report, "run", fake_run)

    result = AllowanceGuardianBot().run(_context(), AllowanceGuardianBot.settings_model())

    assert result.status == "partial"
    assert [row["owner"] for row in result.report["owners"]] == ["alex"]
    assert result.report["failed"] == [{"owner": "sam", "error": "ValueError: schedule unreadable"}]
    assert result.summary == "0 alerts (0 critical) across 1 owner; 1 failed"


def test_every_owner_failing_is_failed(monkeypatch):
    def boom(owner):
        raise ValueError("nope")

    monkeypatch.setattr(guardian_report, "run", boom)

    result = AllowanceGuardianBot().run(_context("alex"), AllowanceGuardianBot.settings_model())

    assert result.status == "failed"


def test_no_owners_is_skipped(monkeypatch):
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: [])

    result = AllowanceGuardianBot().run(_context(), AllowanceGuardianBot.settings_model())

    assert (result.status, result.summary) == ("skipped", "No owners found")
