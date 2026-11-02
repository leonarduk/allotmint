"""Where contribution schedules are stored (#10495)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.allowance_guardian import report
from backend.allowance_guardian.schedule import (
    ContributionSchedule,
    ScheduledContribution,
    load_schedule,
    save_schedule,
)
from backend.common import dividends
from backend.common.accounts_store import S3AccountsStore
from backend.config import config
from tests.backend.fake_s3 import FakeS3


def _schedule(owner: str = "alex") -> ContributionSchedule:
    item = ScheduledContribution(
        account="sipp", amount_minor=50_000, source="employer", expected_day=28, start_date=date(2026, 4, 1)
    )
    return ContributionSchedule(owner=owner, contributions=[item])


def test_schedule_is_saved_locally_without_the_uri(monkeypatch, tmp_path):
    monkeypatch.delenv("CONTRIBUTION_SCHEDULES_URI", raising=False)
    schedule = _schedule()

    assert save_schedule(schedule, tmp_path) == tmp_path / "contribution_schedules" / "alex.json"
    assert load_schedule("alex", tmp_path) == schedule
    assert not list((tmp_path / "contribution_schedules").glob("*.tmp"))


def test_schedule_round_trips_through_s3_when_the_uri_is_set(monkeypatch, tmp_path):
    """On AWS the schedule lives in the bucket, not the Lambda's ephemeral /tmp/data (#10495)."""
    fake = FakeS3()
    monkeypatch.setenv("CONTRIBUTION_SCHEDULES_URI", "s3://data-bucket/contribution_schedules")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: fake)
    schedule = _schedule()

    assert save_schedule(schedule, tmp_path) is None
    assert list(fake.objects) == [("data-bucket", "contribution_schedules/alex.json")]
    assert load_schedule("alex", tmp_path) == schedule
    assert not (tmp_path / "contribution_schedules").exists()
    assert load_schedule("bob", tmp_path) == ContributionSchedule(owner="bob")


def test_schedule_read_error_in_s3_is_not_read_as_an_empty_schedule(monkeypatch, tmp_path):
    from botocore.exceptions import ClientError

    monkeypatch.setenv("CONTRIBUTION_SCHEDULES_URI", "s3://data-bucket/contribution_schedules")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: FakeS3(fail_with="AccessDenied"))
    with pytest.raises(ClientError):
        load_schedule("alex", tmp_path)


@pytest.mark.parametrize("owner", ["../alex", "a/b", ""])
def test_owner_ids_cannot_escape_the_schedules_dir(monkeypatch, tmp_path, owner):
    monkeypatch.delenv("CONTRIBUTION_SCHEDULES_URI", raising=False)
    with pytest.raises(ValueError):
        load_schedule(owner, tmp_path)


def _capture_store(monkeypatch):
    seen = {}

    def fake_load_all_transactions(store=None):
        seen["store"] = store
        return []

    monkeypatch.setattr("backend.routes.transactions.load_all_transactions", fake_load_all_transactions)
    return seen


@pytest.mark.parametrize(
    ("app_env", "bucket"),
    [("aws", "data-bucket"), ("local", "data-bucket"), ("local", None), ("aws", None)],
)
def test_transactions_store_matches_dividends_resolve_store(monkeypatch, app_env, bucket):
    """On AWS the owners' transactions are only in writable-accounts/; same rule as #11175."""
    seen = _capture_store(monkeypatch)
    monkeypatch.setattr(config, "app_env", app_env, raising=False)
    if bucket is None:
        monkeypatch.delenv("DATA_BUCKET", raising=False)
    else:
        monkeypatch.setenv("DATA_BUCKET", bucket)

    assert report._owner_transactions("alex") == []
    resolved = dividends._resolve_store()

    assert isinstance(seen["store"], S3AccountsStore) == isinstance(resolved, S3AccountsStore)
    if isinstance(resolved, S3AccountsStore):
        assert seen["store"].bucket == resolved.bucket == bucket
    else:
        assert seen["store"] is None
