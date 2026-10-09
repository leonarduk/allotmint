"""The statement-reconciliation bot: registration and PII-free run records (#10474, #10477)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.bots import registry, runner, runs
from backend.bots.registry import BotRunContext, BotSettings
from backend.reconciliation import bot
from backend.reconciliation.models import (
    Diff,
    Match,
    ReconciliationResult,
    StatementExtraction,
    StatementRow,
    SuggestedChange,
)


def _result(rows: int = 2, diffs: int = 1) -> ReconciliationResult:
    return ReconciliationResult(
        extracted=StatementExtraction(
            rows=[
                StatementRow(
                    index=i, date=date(2026, 1, 1), type="INTEREST", description="Secret 1234", amount_minor=123
                )
                for i in range(rows)
            ]
        ),
        matched=[Match(statement_index=0, ledger_id="alice:isa:0")] if rows else [],
        diffs=[
            Diff(kind="fee_mismatch", message="fee 11.95 vs 0", suggestion=SuggestedChange(description="fix 11.95"))
            for _ in range(diffs)
        ],
        warnings=["Row 1 says 9999"],
        llm_provider="bedrock",
        sent_to_cloud=True,
    )


def _context(payload) -> BotRunContext:
    return BotRunContext(
        run_id="r1",
        bot_id=bot.BOT_ID,
        trigger="event",
        started_at=datetime.now(timezone.utc),
        owner="alice",
        payload=payload,
    )


def _run(payload):
    return registry.get_bot(bot.BOT_ID).run(_context(payload), BotSettings())


def test_registered_as_owner_scoped_event_driven_ai_bot():
    registered = registry.get_bot(bot.BOT_ID)

    assert registered.kind == "ai"
    assert registered.scope == "owner"
    assert registered.default_schedule is None
    assert bot.BOT_ID in {b.id for b in registry.list_bots()}


def test_reconciled_payload_holds_counts_only():
    payload = bot.reconciled_payload(_result())

    assert payload == {
        "outcome": "reconciled",
        "rows": 2,
        "matched": 1,
        "differences": 1,
        "warnings": 1,
        "by_kind": {"fee_mismatch": 1},
        "llm_provider": "bedrock",
        "sent_to_cloud": True,
        "explained": False,
    }
    assert not any(value in str(payload) for value in ("Secret", "1234", "11.95", "9999"))


def test_reconciled_run_is_ok_with_count_summary():
    result = _run(bot.reconciled_payload(_result()))

    assert result.status == "ok"
    assert result.summary == "1 matched, 1 differences, 1 warnings"
    assert result.owner == "alice"
    assert result.model == "bedrock"


def test_statement_with_no_rows_is_partial_not_ok():
    result = _run(bot.reconciled_payload(_result(rows=0, diffs=0)))

    assert result.status == "partial"
    assert result.summary == "No rows were read from the statement"


def test_failed_payload_records_the_cause_type():
    try:
        try:
            raise ValueError("statement text 1234")
        except ValueError as cause:
            raise RuntimeError("wrapper with 1234") from cause
    except RuntimeError as exc:
        payload = bot.failed_payload(422, exc, "ollama")

    result = _run(payload)

    assert result.status == "failed"
    assert result.error == "ValueError"
    assert "1234" not in f"{result.summary} {result.error} {result.report}"


def test_manual_run_without_payload_is_skipped():
    result = _run({})

    assert result.status == "skipped"
    assert "uploaded" in result.summary


def test_payload_with_extra_fields_is_refused_not_stored():
    payload = {**bot.reconciled_payload(_result()), "message": "Debit card 3990"}

    result = _run(payload)

    assert result.status == "failed"
    assert result.error == "ValidationError"
    assert result.report is None
    assert "3990" not in f"{result.summary} {result.error}"


def test_unexpected_error_inside_run_is_recorded_as_type_only(monkeypatch):
    def boom(context):
        raise RuntimeError("statement says 3990.55")

    monkeypatch.setattr(bot, "_result", boom)

    record, _ = runner.execute(bot.BOT_ID, "event", owner="alice", payload={"anything": 1})

    assert record.status == "failed"
    assert record.error == "RuntimeError"
    # Match the message text, not bare digits: timestamps in the record can contain "3990" (#10549).
    assert "3990.55" not in record.model_dump_json()
    assert runs.latest_run(bot.BOT_ID).id == record.id


def test_execute_records_one_event_run_per_call():
    payload = bot.reconciled_payload(_result())

    first, _ = runner.execute(bot.BOT_ID, "event", owner="alice", actor="alice", payload=payload)
    second, _ = runner.execute(bot.BOT_ID, "event", owner="alice", actor="alice", payload=payload)

    assert [r.id for r in runs.list_runs(bot.BOT_ID)] == [second.id, first.id]
    assert first.actor == "alice" and first.owner == "alice"


def test_enabled_check_fails_open_when_settings_cannot_be_read(monkeypatch, caplog):
    from backend.bots import settings

    def broken(_bot):
        raise OSError("store down")

    monkeypatch.setattr(settings, "load_settings", broken)

    with caplog.at_level("ERROR"):
        assert bot.reconciliation_enabled() is True
    assert "treating it as enabled" in caplog.text


@pytest.mark.parametrize("enabled", [True, False])
def test_enabled_check_follows_saved_settings(enabled):
    from backend.bots import settings

    settings.save_settings(registry.get_bot(bot.BOT_ID), {"enabled": enabled})

    assert bot.reconciliation_enabled() is enabled
