import importlib
import sys
from datetime import date

import pytest


@pytest.fixture
def quests(tmp_path, monkeypatch):
    """Return a fresh quests module using isolated storage."""
    monkeypatch.setenv("QUESTS_URI", f"file://{tmp_path/'quests.json'}")
    sys.modules.pop("backend.quests", None)
    return importlib.import_module("backend.quests")


def test_get_quests_new_user(quests):
    """New users should see all quests incomplete with zero progress."""
    summary = quests.get_quests("alice")
    assert summary["xp"] == 0
    assert summary["streak"] == 0
    assert {q["completed"] for q in summary["quests"]} == {False}


def test_get_quests_after_completion(quests):
    quests.mark_complete("alice", "check_in")
    summary = quests.get_quests("alice")
    statuses = {q["id"]: q["completed"] for q in summary["quests"]}
    assert summary["xp"] == 10
    assert statuses["check_in"] is True
    assert statuses["read_article"] is False

    # Completing the same quest twice should not grant more XP
    summary = quests.mark_complete("alice", "check_in")
    assert summary["xp"] == 10


def test_mark_complete_updates_xp_and_streak(quests, monkeypatch):
    def set_day(day):
        class DummyDate(date):
            @classmethod
            def today(cls):
                return day
        monkeypatch.setattr(quests, "date", DummyDate)

    # Day one: complete both quests
    set_day(date(2021, 1, 1))
    quests.mark_complete("bob", "check_in")
    summary = quests.mark_complete("bob", "read_article")
    assert summary["xp"] == 30
    assert summary["streak"] == 1

    # Next day: streak should increment
    set_day(date(2021, 1, 2))
    quests.mark_complete("bob", "check_in")
    summary = quests.mark_complete("bob", "read_article")
    assert summary["xp"] == 60
    assert summary["streak"] == 2


def test_mark_complete_invalid_id_raises(quests):
    with pytest.raises(KeyError):
        quests.mark_complete("alice", "does_not_exist")
