"""The allowance guardian on the Bots page (#10495). Synthetic owners and figures only."""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import importers
from backend.allowance_guardian import bot as guardian_bot
from backend.allowance_guardian import report as guardian_report
from backend.allowance_guardian.bot import (
    BOT_ID,
    REASON_RECONCILIATION,
    REASON_TRANSACTION_IMPORT,
    AllowanceGuardianBot,
    AllowanceGuardianSettings,
    run_after_import,
)
from backend.allowance_guardian.schedule import ScheduledContribution
from backend.app import create_app
from backend.bots import registry, runs
from backend.bots.digest_models import DigestItem, Severity
from backend.bots.registry import BotRunContext
from backend.bots.settings import save_settings
from backend.config import config
from backend.routes.transactions import Transaction
from tests.backend.allowance_guardian.test_report import ADVICE_PATTERNS

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


def _synthetic_run(owner, **kwargs):
    return REAL_RUN(owner, today=TODAY, transactions=[], schedule=_schedule(), allowances=_allowances(), **kwargs)


def test_registered_as_an_owner_scoped_rules_bot_with_a_monthly_schedule():
    bot = registry.get_bot(BOT_ID)

    assert isinstance(bot, AllowanceGuardianBot)
    assert (bot.kind, bot.scope) == ("rules", "owner")
    # cdk MonthlyAllowanceGuardianRun: cron(0 4 1 * ? *) (#10495).
    assert bot.default_schedule == registry.Schedule(hour=4, day=1)
    assert bot.default_schedule.description == "Monthly on day 1 at 04:00 UTC"
    settings = bot.settings_model.model_validate(bot.default_settings())
    assert settings.cadence == "monthly"
    assert settings.run_after_import and settings.alerts
    assert settings.isa_deadline_reminder_days == guardian_report.ISA_DEADLINE_REMINDER_DAYS


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
    assert result.report["not_modelled"] == guardian_report.NOT_MODELLED
    assert result.report["adviser_note"] == guardian_report.ADVISER_NOTE
    assert result.summary.startswith(f"{row['alerts']} alerts ({row['critical']} critical) across 1 owner")
    # Alert messages carry amounts; the stored run report holds counts only. The
    # not-modelled list quotes statutory limits (e.g. the MPAA), not owner figures.
    owner_facts = {k: v for k, v in result.report.items() if k != "not_modelled"}
    assert "£" not in json.dumps(owner_facts, ensure_ascii=False)


def test_one_owners_failure_does_not_stop_the_others(monkeypatch):
    plots = [SimpleNamespace(owner="alex"), SimpleNamespace(owner="sam")]
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: plots)

    def fake_run(owner, **kwargs):
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
    def boom(owner, **kwargs):
        raise ValueError("nope")

    monkeypatch.setattr(guardian_report, "run", boom)

    result = AllowanceGuardianBot().run(_context("alex"), AllowanceGuardianBot.settings_model())

    assert result.status == "failed"


def test_no_owners_is_skipped(monkeypatch):
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: [])

    result = AllowanceGuardianBot().run(_context(), AllowanceGuardianBot.settings_model())

    assert (result.status, result.summary) == ("skipped", "No owners found")


def test_settings_reject_an_out_of_range_reminder_window():
    with pytest.raises(ValidationError):
        AllowanceGuardianSettings(isa_deadline_reminder_days=400)


def _items(result):
    return [DigestItem.model_validate(item) for item in result.report["digest_items"]]


def test_projected_breach_raises_an_owner_alert_with_the_breach_month(monkeypatch):
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)

    result = AllowanceGuardianBot().run(_context("alex"), AllowanceGuardianSettings())

    items = {item.dedupe_key: item for item in _items(result)}
    breach = items[f"{BOT_ID}:alex:pension_projected_breach"]
    assert breach.owner == "alex" and breach.bot == BOT_ID
    assert breach.severity == Severity.HIGH and breach.action_required
    assert "2026-10" in breach.title and "2026-10" in breach.summary
    missing = items[f"{BOT_ID}:alex:contribution_missing"]
    assert missing.severity == Severity.MEDIUM
    count = result.report["owners"][0]["contribution_counts"]["missing"]
    assert missing.title == f"{count} expected contribution(s) this tax year: missing"
    assert len(items) == result.report["owners"][0]["alerts"]


def test_digest_items_come_from_the_shared_helper(monkeypatch):
    """Built with run_records.digest_item (#11312): id == dedupe_key and whole-second timestamps."""
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)
    started = datetime(2026, 10, 9, 9, 0, 0, 654321, tzinfo=timezone.utc)
    context = BotRunContext(run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=started, owner="alex")

    items = _items(AllowanceGuardianBot().run(context, AllowanceGuardianSettings()))

    assert items
    for item in items:
        assert item.id == item.dedupe_key and item.dedupe_key.startswith(f"{BOT_ID}:alex:")
        assert (item.owner, item.link, item.created) == ("alex", "/bots", started.replace(microsecond=0))


def test_alert_text_is_factual_and_amount_free():
    row = {
        "owner": "alex",
        "breach_month": "2027-02",
        "carry_forward_month": "2027-01",
        "isa_deadline": "2027-04-05",
        "isa_days_to_deadline": 30,
        "contribution_counts": {"missing": 1, "late": 2, "wrong_amount": 3},
    }
    codes = [
        "pension_projected_breach",
        "pension_over_allowance",
        "pension_carry_forward_needed",
        "isa_over_limit",
        "isa_deadline",
        "contribution_missing",
        "contribution_late",
        "contribution_wrong_amount",
    ]
    for code in codes:
        text = " ".join(guardian_bot._alert_text(code, row))
        assert "£" not in text, code
        assert "None" not in text, code
        assert not [p for p in ADVICE_PATTERNS if re.search(p, text, flags=re.IGNORECASE)], code


def test_alerts_off_stores_the_report_without_digest_items(monkeypatch):
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)

    result = AllowanceGuardianBot().run(_context("alex"), AllowanceGuardianSettings(alerts=False))

    assert result.report["digest_items"] == []
    assert result.report["owners"][0]["codes"]["pension_projected_breach"] == 1


def test_reminder_window_setting_reaches_the_report(monkeypatch):
    seen = {}

    def fake_run(owner, **kwargs):
        seen.update(kwargs)
        return {"tax_year": "2026-2027", "schedule_count": 0, "alerts": [], "pension_allowance": {}}

    monkeypatch.setattr(guardian_report, "run", fake_run)

    AllowanceGuardianBot().run(_context("alex"), AllowanceGuardianSettings(isa_deadline_reminder_days=14))

    assert seen == {"isa_reminder_days": 14}


def test_isa_deadline_alert_follows_the_reminder_window():
    march = date(2027, 3, 1)  # 35 days to 5 April
    schedule = [
        ScheduledContribution(
            account="isa", amount_minor=100_000, source="isa_subscription", expected_day=1, start_date="2026-04-01"
        )
    ]

    def codes(days):
        report = REAL_RUN(
            "alex", today=march, transactions=[], schedule=schedule, allowances=_allowances(), isa_reminder_days=days
        )
        return {alert["code"] for alert in report["alerts"]}

    assert "isa_deadline" in codes(60)
    assert "isa_deadline" not in codes(14)


def test_run_after_import_stores_an_event_run_for_every_owner(monkeypatch):
    plots = [SimpleNamespace(owner="alex"), SimpleNamespace(owner="sam")]
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: plots)
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)

    run_after_import(actor="alex")

    [record] = runs.list_runs(BOT_ID)
    assert (record.trigger, record.status, record.owner, record.actor) == ("event", "ok", None, "alex")
    assert [row["owner"] for row in record.report["owners"]] == ["alex", "sam"]
    assert record.report["not_modelled"] == guardian_report.NOT_MODELLED
    assert record.report["adviser_note"] == guardian_report.ADVISER_NOTE
    assert "pension breach projected 2026-10" in record.summary
    assert record.report["reason"] == REASON_TRANSACTION_IMPORT


def test_run_after_reconciliation_stores_an_event_run_for_every_owner_with_its_reason(monkeypatch):
    plots = [SimpleNamespace(owner="alex"), SimpleNamespace(owner="sam")]
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: plots)
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)

    run_after_import("alex", REASON_RECONCILIATION)

    [record] = runs.list_runs(BOT_ID)
    assert (record.trigger, record.status, record.actor) == ("event", "ok", "alex")
    assert [row["owner"] for row in record.report["owners"]] == ["alex", "sam"]
    assert record.report["reason"] == REASON_RECONCILIATION
    assert record.report["not_modelled"] == guardian_report.NOT_MODELLED


def test_a_manual_run_or_unknown_reason_stores_no_reason(monkeypatch):
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)
    bot = AllowanceGuardianBot()
    context = dataclasses.replace(_context("alex"), payload={"reason": "<script>"})

    assert bot.run(_context("alex"), AllowanceGuardianSettings()).report["reason"] is None
    assert bot.run(context, AllowanceGuardianSettings()).report["reason"] is None


@pytest.mark.parametrize("reason", [REASON_TRANSACTION_IMPORT, REASON_RECONCILIATION])
@pytest.mark.parametrize("values", [{"enabled": False}, {"run_after_import": False}])
def test_run_after_import_does_nothing_when_switched_off(monkeypatch, values, reason):
    monkeypatch.setattr(guardian_report, "run", _synthetic_run)
    bot = registry.get_bot(BOT_ID)
    save_settings(bot, {**bot.default_settings(), **values})

    run_after_import(None, reason)

    assert runs.list_runs(BOT_ID) == []


@pytest.mark.parametrize("reason", [REASON_TRANSACTION_IMPORT, REASON_RECONCILIATION])
def test_run_after_import_never_raises(monkeypatch, caplog, reason):
    def broken(_bot):
        raise OSError("store down")

    monkeypatch.setattr("backend.bots.settings.load_settings", broken)

    run_after_import(None, reason)

    assert "run after import failed: OSError" in caplog.text
    assert f"(reason {reason})" in caplog.text


def test_transaction_import_runs_the_guardian_afterwards(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    calls = []
    monkeypatch.setattr(guardian_bot, "run_after_import", lambda actor=None: calls.append(actor))
    row = Transaction(owner="alex", account="ISA", date="2024-05-01", ticker="PFE", type="BUY", price=10.5, units=2)
    client = TestClient(create_app())

    monkeypatch.setattr(importers, "parse", lambda provider, data: [])
    empty = client.post("/transactions/import", data={"provider": "test"}, files={"file": ("t.csv", b"x", "text/csv")})
    assert empty.status_code == 200 and calls == []

    monkeypatch.setattr(importers, "parse", lambda provider, data: [row])
    resp = client.post("/transactions/import", data={"provider": "test"}, files={"file": ("t.csv", b"x", "text/csv")})

    assert resp.status_code == 200 and len(resp.json()["persisted"]) == 1
    assert calls == [None]


def test_lambda_handler_runs_the_bot_through_the_runner(monkeypatch):
    from backend.lambda_api import allowance_guardian as lambda_handler

    seen = []

    def fake_handle(bot_id, event, *, reraise=False):
        seen.append((bot_id, event, reraise))
        return {"bot": bot_id}

    monkeypatch.setattr(lambda_handler, "handle_lambda_event", fake_handle)

    event = {"bot_run_id": "r1"}
    assert lambda_handler.lambda_handler(event, None) == {"status": "ok"}
    assert seen == [(BOT_ID, event, True)]


def test_lambda_handler_reports_a_skipped_scheduled_run(monkeypatch):
    from backend.lambda_api import allowance_guardian as lambda_handler

    monkeypatch.setattr(
        lambda_handler,
        "handle_lambda_event",
        lambda bot_id, event, *, reraise=False: {"skipped": True, "reason": "Disabled", "run_id": "r1"},
    )

    assert lambda_handler.lambda_handler({"source": "aws.events"}, None) == {"status": "skipped", "reason": "Disabled"}
