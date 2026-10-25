"""Cash deployment tracker on the Bots page (#10505). Synthetic owners and figures only."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.bots import registry
from backend.bots.registry import BotRunContext, is_valid_bot_id
from backend.cash_deployment import bot as bot_module
from backend.cash_deployment.bot import BOT_ID, CashDeploymentBot
from backend.cash_deployment.schedule import ScheduleInput, create_schedule
from backend.common import holding_utils
from tests.backend.cash_deployment.fixtures import synthetic_plan, synthetic_portfolio

AS_OF = datetime(2026, 1, 15, 9, tzinfo=timezone.utc)


def _context(owner=None):
    return BotRunContext(run_id="r1", bot_id=BOT_ID, trigger="manual", started_at=AS_OF, owner=owner)


@pytest.fixture
def accounts(monkeypatch, tmp_path):
    """``alex`` with one ISA, a saved plan and the synthetic portfolio; no schedule yet."""
    root = tmp_path / "accounts"
    (root / "alex").mkdir(parents=True)
    (root / "alex" / "isa.json").write_text(json.dumps({"account_type": "ISA", "holdings": []}))
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(synthetic_plan().to_dict()))
    monkeypatch.setattr(bot_module, "resolve_default_accounts_root", lambda: root)
    monkeypatch.setattr(bot_module.portfolio_mod, "build_owner_portfolio", lambda *a, **k: synthetic_portfolio())
    monkeypatch.setattr(holding_utils, "load_latest_prices", lambda tickers: {"VWX.L": 10.0})
    return root


def _add_schedule(root, status="active"):
    body = ScheduleInput(
        account="isa",
        total_amount_minor=1_200_000,
        tranches=12,
        cadence="monthly",
        start_date=date(2026, 1, 15),
        target_source="plan",
        status=status,
    )
    create_schedule("alex", body, root)


def test_registered_as_a_daily_owner_scoped_rules_bot_without_a_schedule():
    bot = registry.get_bot(BOT_ID)

    assert is_valid_bot_id(BOT_ID)
    assert isinstance(bot, CashDeploymentBot)
    assert (bot.kind, bot.scope) == ("rules", "owner")
    assert bot.default_schedule is None
    assert bot.settings_model.model_validate(bot.default_settings()).model_dump() == {
        "enabled": True,
        "cadence": "daily",
    }


def test_run_for_one_owner_matches_the_card_and_stores_counts_only(accounts):
    _add_schedule(accounts)

    result = CashDeploymentBot().run(_context("alex"), CashDeploymentBot.settings_model())

    assert result.status == "ok"
    assert result.summary == "1 tranche(s) due now, 0 overdue across 1 owner"
    assert result.report == {
        "owners": [
            {
                "owner": "alex",
                "status": "ok",
                "summary": "1 tranche(s) due now, 0 overdue across 1 schedule(s)",
                "schedules": 1,
                "tranches_due": 1,
                "overdue": 0,
            }
        ],
        "failed": [],
    }
    assert "amount_minor" not in json.dumps(result.report)
    # Run now returns the same run as GET /cash-deployment/{owner} for that day.
    assert result.raw == [bot_module.run("alex", AS_OF.date())]


def test_no_active_schedule_is_skipped(accounts):
    _add_schedule(accounts, status="paused")

    result = CashDeploymentBot().run(_context("alex"), CashDeploymentBot.settings_model())

    assert result.status == "skipped"
    assert result.report["owners"][0]["status"] == "skipped"


def test_no_owners_is_skipped(monkeypatch):
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: [])

    result = CashDeploymentBot().run(_context(), CashDeploymentBot.settings_model())

    assert (result.status, result.summary) == ("skipped", "No owners found")


def test_one_owners_failure_does_not_stop_the_others(monkeypatch):
    plots = [SimpleNamespace(owner="alex"), SimpleNamespace(owner="sam")]
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: plots)

    def fake_run(owner, as_of):
        if owner == "sam":
            raise ValueError("settings unreadable")
        return {"owner": owner, "status": "ok", "summary": "s", "schedules": []}

    monkeypatch.setattr(bot_module, "run", fake_run)

    result = CashDeploymentBot().run(_context(), CashDeploymentBot.settings_model())

    assert result.status == "partial"
    assert [row["owner"] for row in result.report["owners"]] == ["alex"]
    assert result.report["failed"] == [{"owner": "sam", "error": "ValueError: settings unreadable"}]
    assert result.error == "sam: ValueError: settings unreadable"


def test_every_owner_failing_is_failed(monkeypatch):
    def boom(owner, as_of):
        raise ValueError("nope")

    monkeypatch.setattr(bot_module, "run", boom)

    result = CashDeploymentBot().run(_context("alex"), CashDeploymentBot.settings_model())

    assert result.status == "failed"


def test_any_partial_owner_makes_the_run_partial(monkeypatch):
    plots = [SimpleNamespace(owner="alex"), SimpleNamespace(owner="sam")]
    monkeypatch.setattr("backend.common.data_loader.list_plots", lambda: plots)
    statuses = {"alex": "ok", "sam": "partial"}
    monkeypatch.setattr(
        bot_module,
        "run",
        lambda owner, as_of: {"owner": owner, "status": statuses[owner], "summary": "s", "schedules": []},
    )

    result = CashDeploymentBot().run(_context(), CashDeploymentBot.settings_model())

    assert result.status == "partial"
