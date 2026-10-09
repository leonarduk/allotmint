"""Bots digest composer (#10485). Synthetic run records only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest

from backend.bots import digest as digest_mod
from backend.bots.digest import compose_digest, opener_is_grounded
from backend.bots.digest_models import BotDescriptor, BotRunRecord, DigestItem, Severity
from backend.bots.run_records import RegistryRunRecordSource

NOW = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)

BOTS = [
    BotDescriptor(id="steward", name="Data steward", kind="ai", scope="system"),
    BotDescriptor(id="guardian", name="Allowance guardian", kind="rules", scope="owner"),
    BotDescriptor(id="cash", name="Cash deployment", kind="rules", scope="owner"),
    BotDescriptor(id="journal", name="Decision journal", kind="ai", scope="owner"),
]


class FakeSource:
    def __init__(self, records: Dict[str, Optional[BotRunRecord]], bots: List[BotDescriptor] = BOTS):
        self._records = records
        self._bots = bots

    def bots(self) -> List[BotDescriptor]:
        return list(self._bots)

    def latest_run(self, bot_id: str) -> Optional[BotRunRecord]:
        return self._records.get(bot_id)


def _item(
    bot: str, key: str, *, owner: Optional[str] = "alex", severity=Severity.LOW, action=False, age_days=1, title=None
):
    return DigestItem(
        id=f"{bot}-{key}",
        bot=bot,
        owner=owner,
        severity=severity,
        title=title or f"{bot} finding {key}",
        summary="",
        action_required=action,
        created=NOW - timedelta(days=age_days),
        dedupe_key=f"{bot}:{key}",
    )


def _run(bot: str, items: List[DigestItem], status="ok") -> BotRunRecord:
    return BotRunRecord(bot_id=bot, status=status, started_at=NOW - timedelta(hours=2), digest_items=items)


def _three_bot_records():
    return {
        "steward": _run("steward", [_item("steward", "split", owner=None, severity=Severity.MEDIUM, action=True)]),
        "guardian": _run(
            "guardian",
            [
                _item("guardian", "sept-missing", severity=Severity.HIGH, action=True),
                _item("guardian", "isa-headroom", severity=Severity.LOW),
            ],
        ),
        "cash": _run(
            "cash",
            [
                _item("cash", "tranche-3", severity=Severity.MEDIUM, action=False, age_days=5),
                _item("cash", "tranche-2", severity=Severity.MEDIUM, action=True, age_days=1),
                _item("cash", "other-owner", owner="bob", severity=Severity.HIGH),
            ],
        ),
    }


def _compose(records, **kwargs):
    kwargs.setdefault("previous", None)
    kwargs.setdefault("now", NOW)
    return compose_digest("alex", FakeSource(records), **kwargs)


def test_ranks_by_severity_then_action_then_age():
    digest = _compose(_three_bot_records())
    keys = [i.dedupe_key for i in digest.items]
    assert keys == ["guardian:sept-missing", "cash:tranche-2", "cash:tranche-3", "guardian:isa-headroom"]


def test_other_owners_items_never_appear():
    digest = _compose(_three_bot_records(), include_system=True)
    assert all(i.owner in ("alex", None) for i in digest.items)
    assert "cash:other-owner" not in {i.dedupe_key for i in digest.items}


def test_system_items_only_for_admins():
    assert "steward:split" not in {i.dedupe_key for i in _compose(_three_bot_records()).items}
    admin = _compose(_three_bot_records(), include_system=True)
    assert "steward:split" in {i.dedupe_key for i in admin.items}


def test_new_still_open_and_resolved_across_digests():
    first = _compose(_three_bot_records())
    assert {i.status for i in first.items} == {"new"}

    records = _three_bot_records()
    records["guardian"] = _run("guardian", [_item("guardian", "sept-missing", severity=Severity.HIGH, action=True)])
    records["cash"].digest_items.append(_item("cash", "tranche-4", severity=Severity.LOW))
    second = _compose(records, previous=first)

    status = {i.dedupe_key: i.status for i in second.items}
    assert status["guardian:sept-missing"] == "still_open"
    assert status["cash:tranche-4"] == "new"
    assert [r.dedupe_key for r in second.resolved] == ["guardian:isa-headroom"]
    assert second.resolved[0].status == "resolved"

    # Resolved items appear once, then drop out.
    third = _compose(records, previous=second)
    assert third.resolved == []
    assert {i.status for i in third.items} == {"still_open"}


def test_still_open_item_keeps_its_first_seen_age():
    """A re-reported finding (e.g. a job failing every run) keeps the age it was first shown with."""

    records = {"guardian": _run("guardian", [], status="failed")}
    first = _compose(records)
    records["guardian"] = BotRunRecord(bot_id="guardian", status="failed", started_at=NOW + timedelta(days=3))
    second = _compose(records, previous=first)
    assert second.items[0].status == "still_open"
    assert second.items[0].created == first.items[0].created


def test_bot_without_runs_is_not_run_yet_not_an_error():
    digest = _compose(_three_bot_records())
    states = {b.bot: b.state for b in digest.bots}
    assert states == {"steward": "ok", "guardian": "ok", "cash": "ok", "journal": "not_run_yet"}


def test_zero_bots_with_runs_says_nothing_needs_you():
    digest = _compose({})
    assert digest.items == []
    assert digest.opener == "Nothing needs you right now."
    assert {b.state for b in digest.bots} == {"not_run_yet"}


def test_failed_scheduled_job_is_high_severity_item():
    records = {"guardian": _run("guardian", [], status="failed")}
    digest = _compose(records)
    assert len(digest.items) == 1
    item = digest.items[0]
    assert (item.severity, item.action_required, item.owner) == (Severity.HIGH, True, "alex")
    assert item.title == "Allowance guardian run failed"

    # A failed system job is system-wide: admins only.
    system = {"steward": _run("steward", [], status="failed")}
    assert _compose(system).items == []
    assert _compose(system, include_system=True).items[0].dedupe_key == "steward:run-failed"


def test_per_bot_cap_counts_dropped_items_and_keeps_them_open():
    records = {"cash": _run("cash", [_item("cash", f"t{n}", age_days=n) for n in range(4)])}
    first = _compose(records, per_bot_cap=2)
    assert len(first.items) == 2
    assert first.truncated == {"cash": 2}
    # A capped item is still open: not "new" next time.
    records["cash"].digest_items = records["cash"].digest_items[2:]
    second = _compose(records, previous=first, per_bot_cap=2)
    assert {i.status for i in second.items} == {"still_open"}


def test_duplicate_keys_keep_highest_severity():
    records = {
        "cash": _run(
            "cash",
            [_item("cash", "dup", severity=Severity.LOW), _item("cash", "dup", severity=Severity.HIGH)],
        )
    }
    digest = _compose(records)
    assert [(i.dedupe_key, i.severity) for i in digest.items] == [("cash:dup", Severity.HIGH)]


def test_naive_and_aware_timestamps_compare():
    naive = _item("cash", "naive").model_copy(update={"created": datetime(2026, 10, 1)})
    items = [_item("cash", "aware"), DigestItem.model_validate(naive.model_dump())]
    digest = _compose({"cash": _run("cash", items)})
    assert [i.dedupe_key for i in digest.items] == ["cash:naive", "cash:aware"]


def test_composition_is_deterministic():
    assert _compose(_three_bot_records()) == _compose(_three_bot_records())


# --- LLM opener grounding --------------------------------------------------


def _opener_items():
    records = {
        "guardian": _run(
            "guardian",
            [
                _item(
                    "guardian", "sept", severity=Severity.HIGH, action=True, title="September contribution not received"
                )
            ],
        ),
        "cash": _run("cash", [_item("cash", "t3", severity=Severity.MEDIUM, title="Tranche 3 due Monday")]),
    }
    return records


def test_grounded_llm_opener_is_used():
    def opener(items, resolved):
        return "2 items need you. Tranche 3 is due Monday and the September contribution has not arrived."

    digest = _compose(_opener_items(), opener_fn=opener)
    assert digest.opener.startswith("2 items need you.")


@pytest.mark.parametrize(
    "invented",
    [
        "Tranche 3 of £12,000 is due Monday.",
        "You are 4.1pp over target.",
        "7 items need you.",
    ],
)
def test_opener_with_a_number_absent_from_items_is_rejected(invented):
    digest = _compose(_opener_items(), opener_fn=lambda items, resolved: invented)
    assert digest.opener == digest_mod.deterministic_opener(digest.items, digest.resolved)
    assert not opener_is_grounded(invented, digest.items, digest.resolved)


def test_failing_opener_falls_back():
    def boom(items, resolved):
        raise RuntimeError("provider down")

    digest = _compose(_opener_items(), opener_fn=boom)
    assert digest.opener == digest_mod.deterministic_opener(digest.items, digest.resolved)


def test_deterministic_opener_is_grounded():
    digest = _compose(_three_bot_records())
    assert opener_is_grounded(digest.opener, digest.items, digest.resolved)


# --- registry-backed run record source --------------------------------------


def _registry_run(bot_id, status, *, report=None, minutes_ago=60):
    from backend.bots import runs

    return runs.save_run(
        runs.RunRecord(
            id=f"{bot_id}-{status}-{minutes_ago}",
            bot_id=bot_id,
            trigger="schedule",
            status=status,
            started_at=NOW - timedelta(minutes=minutes_ago),
            summary=f"{status} run",
            report=report,
        )
    )


def test_registry_source_lists_registered_bots(fake_bot):
    bots = {b.id: b for b in RegistryRunRecordSource().bots()}
    assert bots["fake-bot"] == BotDescriptor(id="fake-bot", name="Fake bot", kind="job", scope="system")
    assert "price-refresh" in bots


def test_registry_source_reads_digest_items_from_report(fake_bot):
    good = _item("fake-bot", "t1").model_dump(mode="json")
    _registry_run("fake-bot", "ok", report={"digest_items": [good, {"title": "no key or created"}]})

    record = RegistryRunRecordSource().latest_run("fake-bot")
    assert record.status == "ok"
    assert record.summary == "ok run"
    # The malformed item is skipped; the valid one is kept.
    assert [i.dedupe_key for i in record.digest_items] == ["fake-bot:t1"]


def test_registry_source_skips_a_run_in_progress(fake_bot):
    assert RegistryRunRecordSource().latest_run("fake-bot") is None
    _registry_run("fake-bot", "failed", minutes_ago=120)
    _registry_run("fake-bot", "running", minutes_ago=1)
    assert RegistryRunRecordSource().latest_run("fake-bot").status == "failed"


def test_registry_source_without_report_has_no_items(fake_bot):
    _registry_run("fake-bot", "ok", report=None)
    assert RegistryRunRecordSource().latest_run("fake-bot").digest_items == []


@pytest.mark.parametrize("segment", ["../secrets", "..", "a/b", "", ".hidden"])
def test_storage_rejects_unsafe_path_segments(segment):
    from backend.bots.storage import safe_segment

    with pytest.raises(ValueError):
        safe_segment(segment)


def test_registry_source_uses_the_newest_finished_run(fake_bot):
    # Saved oldest-last on purpose: the registry keeps runs newest first.
    _registry_run("fake-bot", "ok", minutes_ago=10)
    _registry_run("fake-bot", "failed", minutes_ago=300)
    record = RegistryRunRecordSource().latest_run("fake-bot")
    assert (record.status, record.started_at) == ("ok", NOW - timedelta(minutes=10))
