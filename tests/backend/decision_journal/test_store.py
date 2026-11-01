"""Where decision journals live (#11159): DECISION_JOURNAL_URI, else <data_root>/decision_journal."""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError

from backend.decision_journal import bot as bot_mod
from backend.decision_journal.store import Journal, load_journal, save_journal
from tests.backend.decision_journal.fixtures import sell_entry
from tests.backend.fake_s3 import FakeS3


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setenv("DECISION_JOURNAL_URI", "s3://data-bucket/decision_journal")
    monkeypatch.setenv("PLANS_URI", "s3://data-bucket/plans")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: fake)
    return fake


def test_local_default_is_beside_plans(monkeypatch, tmp_path):
    monkeypatch.delenv("DECISION_JOURNAL_URI", raising=False)
    journal = Journal(owner="alex", entries=[sell_entry()])
    assert save_journal(journal, tmp_path) == tmp_path / "decision_journal" / "alex.json"
    assert load_journal("alex", tmp_path) == journal


def test_s3_round_trip_through_the_bucket(s3, tmp_path):
    """The API Lambda and a scheduled run read and write the same bucket key, never data_root."""
    assert load_journal("alex", tmp_path) == Journal(owner="alex")
    journal = Journal(owner="alex", entries=[sell_entry()])

    assert save_journal(journal, tmp_path) is None

    assert list(s3.objects) == [("data-bucket", "decision_journal/alex.json")]
    assert json.loads(s3.objects[("data-bucket", "decision_journal/alex.json")])["owner"] == "alex"
    assert load_journal("alex", tmp_path) == journal
    assert not (tmp_path / "decision_journal").exists()


def test_s3_read_error_raises_so_a_save_cannot_overwrite_the_journal(monkeypatch, tmp_path):
    monkeypatch.setenv("DECISION_JOURNAL_URI", "s3://data-bucket/decision_journal")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: FakeS3(fail_with="InternalError"))
    with pytest.raises(ClientError):
        load_journal("alex", tmp_path)


def test_known_owners_lists_both_s3_prefixes(s3, tmp_path):
    s3.objects[("data-bucket", "plans/alex.json")] = b"{}"
    s3.objects[("data-bucket", "decision_journal/bob.json")] = b"{}"
    s3.objects[("data-bucket", "decision_journal/alex.json")] = b"{}"
    assert bot_mod.known_owners(tmp_path) == ["alex", "bob"]


@pytest.mark.parametrize("owner", ["../evil", "", "a/b"])
def test_invalid_owner_is_rejected_in_s3_mode(s3, tmp_path, owner):
    with pytest.raises(ValueError):
        load_journal(owner, tmp_path)
    assert s3.objects == {}
