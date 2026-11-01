"""Tests for per-user last-visit storage (#11195)."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from backend.common import last_visit as lv
from backend.common import watchlists as wl

ALICE = "alice@example.com"
BOB = "bob@example.com"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path) -> wl.FileWatchlistsStore:
    return wl.FileWatchlistsStore(root=tmp_path)


def _doc(tmp_path: Path, email: str = ALICE) -> dict:
    return json.loads((tmp_path / f"{lv.user_key(email)}.json").read_text())


def test_first_visit_has_no_previous(store) -> None:
    record = lv.record_visit(ALICE, "family", now=T0, store=store)
    assert record == lv.VisitRecord(previous=None, current=T0)


def test_a_visit_after_the_session_gap_rolls_the_last_one_into_previous(store) -> None:
    lv.record_visit(ALICE, "family", now=T0, store=store)
    later = T0 + timedelta(days=3)
    assert lv.record_visit(ALICE, "family", now=later, store=store) == lv.VisitRecord(previous=T0, current=later)


def test_a_reload_within_the_session_gap_keeps_the_previous_visit(store) -> None:
    lv.record_visit(ALICE, "family", now=T0, store=store)
    second = T0 + timedelta(days=3)
    lv.record_visit(ALICE, "family", now=second, store=store)
    reload = second + timedelta(minutes=5)
    assert lv.record_visit(ALICE, "family", now=reload, store=store).previous == T0


def test_records_are_per_user_and_per_group(store, tmp_path: Path) -> None:
    lv.record_visit(ALICE, "family", now=T0, store=store)
    later = T0 + timedelta(days=2)
    assert lv.record_visit(BOB, "family", now=later, store=store).previous is None
    assert lv.record_visit(ALICE, "adults", now=later, store=store).previous is None
    assert set(_doc(tmp_path)["groups"]) == {"family", "adults"}


def test_files_are_named_by_the_email_hash_and_hold_utc_instants(store, tmp_path: Path) -> None:
    lv.record_visit(ALICE, "family", now=T0, store=store)
    [path] = list(tmp_path.iterdir())
    assert path.name == f"{lv.user_key(ALICE)}.json"
    assert ALICE not in path.read_text()
    assert _doc(tmp_path)["groups"]["family"] == {"previous": None, "current": "2026-10-01T09:00:00+00:00"}


def test_dismissal_clears_previous_and_the_next_session_starts_from_it(store) -> None:
    lv.record_visit(ALICE, "family", now=T0, store=store)
    dismissed_at = T0 + timedelta(days=3)
    assert lv.dismiss_visit(ALICE, "family", now=dismissed_at, store=store).previous is None
    reload = dismissed_at + timedelta(minutes=1)
    assert lv.record_visit(ALICE, "family", now=reload, store=store).previous is None
    next_day = dismissed_at + timedelta(days=1)
    assert lv.record_visit(ALICE, "family", now=next_day, store=store).previous == reload


def test_a_seed_is_used_only_when_nothing_is_stored(store) -> None:
    seed = {"previous": None, "current": "2026-09-28T09:00:00Z"}
    record = lv.record_visit(ALICE, "family", seed=seed, now=T0, store=store)
    assert record.previous == datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)

    later = T0 + timedelta(days=1)
    ignored = {"previous": None, "current": "2020-01-01T00:00:00Z"}
    assert lv.record_visit(ALICE, "family", seed=ignored, now=later, store=store).previous == T0


@pytest.mark.parametrize(
    "seed",
    [
        {"previous": None, "current": "2027-01-01T00:00:00Z"},  # from the future
        {"previous": None, "current": "not a date"},
        {"previous": None, "current": "2026-09-28T09:00:00"},  # no timezone
    ],
)
def test_an_unusable_seed_is_a_first_visit(store, seed) -> None:
    assert lv.record_visit(ALICE, "family", seed=seed, now=T0, store=store).previous is None


def test_a_malformed_group_entry_is_a_first_visit(store, tmp_path: Path) -> None:
    path = tmp_path / f"{lv.user_key(ALICE)}.json"
    path.write_text(json.dumps({"version": 1, "groups": {"family": {"current": 5}}}))
    assert lv.record_visit(ALICE, "family", now=T0, store=store).previous is None


@pytest.mark.parametrize("raw", [b"{not json", b"[]", b'{"groups": []}'])
def test_a_damaged_document_is_unavailable_and_never_overwritten(store, tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / f"{lv.user_key(ALICE)}.json"
    path.write_bytes(raw)
    with pytest.raises(lv.LastVisitUnavailable):
        lv.record_visit(ALICE, "family", now=T0, store=store)
    assert path.read_bytes() == raw


def test_the_least_recently_visited_groups_are_dropped_past_the_cap(store, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lv, "MAX_GROUPS", 2)
    for i, slug in enumerate(["a", "b", "c"]):
        lv.record_visit(ALICE, slug, now=T0 + timedelta(days=i), store=store)
    assert set(_doc(tmp_path)["groups"]) == {"b", "c"}


def test_a_concurrent_write_is_retried_on_the_fresh_copy(store, tmp_path: Path, monkeypatch) -> None:
    lv.record_visit(ALICE, "family", now=T0, store=store)
    real_write = store.write
    calls = {"n": 0}

    def racing_write(key, data, *, expect_tag):
        calls["n"] += 1
        if calls["n"] == 1:
            # Another device lands first: it also visited "family" and "other".
            doc = json.loads(data)
            doc["groups"]["other"] = doc["groups"]["family"]
            real_write(key, json.dumps(doc).encode(), expect_tag=expect_tag)
        real_write(key, data, expect_tag=expect_tag)

    monkeypatch.setattr(store, "write", racing_write)
    later = T0 + timedelta(days=2)
    assert lv.record_visit(ALICE, "family", now=later, store=store).previous == T0
    assert calls["n"] == 2
    assert set(_doc(tmp_path)["groups"]) == {"family", "other"}


def test_a_write_that_keeps_losing_is_unavailable(store, monkeypatch) -> None:
    def always_lose(key, data, *, expect_tag):
        raise wl._PreconditionFailed()

    monkeypatch.setattr(store, "write", always_lose)
    with pytest.raises(lv.LastVisitUnavailable):
        lv.record_visit(ALICE, "family", now=T0, store=store)


def test_default_store_sits_under_the_watchlists_prefix_on_aws(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LAST_VISIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "data-bkt")
    default = lv.get_last_visit_store()
    assert isinstance(default, wl.S3WatchlistsStore)
    assert (default.bucket, default.prefix) == ("data-bkt", "watchlists/last_visit")

    monkeypatch.delenv("DATA_BUCKET")
    monkeypatch.setattr(lv.config, "data_root", tmp_path)
    assert lv.get_last_visit_store().root == tmp_path / "last_visit"


# --- S3 ---------------------------------------------------------------------


def _s3_store():
    client = boto3.client("s3", region_name="eu-west-2", aws_access_key_id="x", aws_secret_access_key="x")
    return wl.S3WatchlistsStore(bucket="bkt", prefix="watchlists/last_visit", client=client), Stubber(client)


def _key(email: str) -> str:
    return f"watchlists/last_visit/{lv.user_key(email)}.json"


def test_s3_first_visit_writes_only_if_the_key_is_still_absent() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_response(
        "put_object",
        {},
        {"Bucket": "bkt", "Key": _key(ALICE), "Body": ANY, "ContentType": "application/json", "IfNoneMatch": "*"},
    )
    with stub:
        assert lv.record_visit(ALICE, "family", now=T0, store=store).previous is None
    stub.assert_no_pending_responses()


def test_s3_update_is_conditional_on_the_etag() -> None:
    store, stub = _s3_store()
    raw = json.dumps({"version": 1, "groups": {"family": {"previous": None, "current": T0.isoformat()}}}).encode()
    stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(raw), len(raw)), "ETag": '"e1"'})
    stub.add_response(
        "put_object",
        {},
        {"Bucket": "bkt", "Key": _key(ALICE), "Body": ANY, "ContentType": "application/json", "IfMatch": '"e1"'},
    )
    with stub:
        assert lv.record_visit(ALICE, "family", now=T0 + timedelta(days=1), store=store).previous == T0
    stub.assert_no_pending_responses()


def test_s3_access_denied_is_unavailable() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
    with stub, pytest.raises(lv.LastVisitUnavailable):
        lv.record_visit(ALICE, "family", now=T0, store=store)
