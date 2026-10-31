"""The decision journal as a registered bot (#10481, #10477). Synthetic owner and tickers only."""

from __future__ import annotations

import functools
import json
from datetime import date, datetime, timezone

from backend.bots import registry, runner
from backend.bots.registry import BotSettings
from backend.common import investment_plan as plan_mod
from backend.decision_journal import bot as bot_mod
from backend.decision_journal import entries as entries_mod
from backend.decision_journal.store import load_journal, save_journal
from tests.backend.decision_journal.fixtures import fake_series, sell_entry

PLAN = {"owner": "alex", "updated": "2026-01-01", "target": [{"class": "equity", "weight_pct": 100}]}
SELL = {
    "id": "alex:isa:9",
    "owner": "alex",
    "date": "2026-07-01",
    "type": "SELL",
    "ticker": "AAA.L",
    "units": 100,
    "price_gbp": 90.0,
}


def test_bot_is_registered_with_the_registry():
    bot = registry.get_bot("decision-journal")
    assert isinstance(bot, registry.Bot)
    assert bot.scope == "system" and bot.kind == "rules"
    assert issubclass(bot.settings_model, BotSettings)
    assert bot.default_settings() == {"enabled": True, "cadence": "daily"}


def test_run_through_the_runner_reports_counts_only_and_never_writes_the_plan(tmp_path, monkeypatch):
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(PLAN), encoding="utf-8")
    journal = load_journal("alex", tmp_path)
    journal.entries.append(sell_entry())
    save_journal(journal, tmp_path)
    before = (tmp_path / "plans" / "alex.json").read_text(encoding="utf-8")

    def refuse(*args, **kwargs):
        raise AssertionError("the bot must never write the plan")

    monkeypatch.setattr(plan_mod, "save_plan", refuse)
    monkeypatch.setattr(entries_mod, "save_plan", refuse)
    monkeypatch.setattr(
        bot_mod,
        "run",
        functools.partial(bot_mod.run, data_root=tmp_path, transactions=[SELL], load_series=fake_series),
    )
    monkeypatch.setattr(runner, "_now", lambda: datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc))

    record, raw = runner.execute("decision-journal", "manual", actor="tester")

    assert record.status == "ok"
    assert record.summary == "1 unlogged trade, 1 review run across 1 owner"
    # The Bots page shows reports to every signed-in user: totals only, no owner
    # names, apart from the owner-scoped digest items, which the Bots API serves
    # only to callers with access to that owner (tests/routes/test_bots.py).
    items = record.report.pop("digest_items")
    assert record.report == {"owners": 1, "unlogged": 1, "reviews_run": 1}
    assert "alex" not in json.dumps(record.report)
    assert [(i["owner"], i["severity"], i["action_required"], i["title"]) for i in items] == [
        ("alex", "low", True, "1 trade not yet logged in your decision journal"),
        ("alex", "info", False, "1 decision review ready"),
    ]
    assert raw["as_of"] == date(2026, 7, 2).isoformat()
    assert (tmp_path / "plans" / "alex.json").read_text(encoding="utf-8") == before
    assert load_journal("alex", tmp_path).entries[0].reviews[0].horizon_months == 6


def _capture_store(monkeypatch):
    seen = {}

    def fake_load_all_transactions(store=None):
        seen["store"] = store
        return []

    monkeypatch.setattr("backend.routes.transactions.load_all_transactions", fake_load_all_transactions)
    return seen


def test_transactions_include_the_writable_s3_store_on_aws(monkeypatch):
    """On AWS the owners' transactions are in writable-accounts/, not the empty /tmp/data (#11159)."""
    from backend.common.accounts_store import S3AccountsStore

    seen = _capture_store(monkeypatch)
    monkeypatch.setattr(bot_mod.config, "app_env", "aws", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "data-bucket")

    assert bot_mod._all_transactions() == []
    assert isinstance(seen["store"], S3AccountsStore) and seen["store"].bucket == "data-bucket"


def test_transactions_read_only_the_local_dataset_off_aws(monkeypatch):
    seen = _capture_store(monkeypatch)
    monkeypatch.setattr(bot_mod.config, "app_env", "local", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "data-bucket")

    bot_mod._all_transactions()
    assert seen["store"] is None
