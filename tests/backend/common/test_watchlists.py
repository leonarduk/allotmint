"""Tests for backend.common.watchlists (#10713)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from pydantic import ValidationError

from backend.common import watchlists as wl

ALICE = "Alice@Example.com"
BOB = "bob@example.com"


def _state(*lists: tuple[str, str, list[str]], active: str | None = None) -> wl.WatchlistsState:
    rows = [{"id": i, "name": n, "symbols": s} for i, n, s in lists] or [
        {"id": "default", "name": "My watchlist", "symbols": ["^FTSE", "VUSA.L"]}
    ]
    return wl.WatchlistsState.model_validate({"activeId": active or rows[0]["id"], "lists": rows})


@pytest.fixture
def store(tmp_path: Path) -> wl.FileWatchlistsStore:
    return wl.FileWatchlistsStore(root=tmp_path)


def test_load_without_saved_watchlists_is_revision_zero_and_no_state(store) -> None:
    assert wl.load_watchlists(ALICE, store) == {"revision": 0, "state": None}


def test_save_then_load_round_trips_and_bumps_the_revision(store) -> None:
    assert wl.save_watchlists(ALICE, _state(), 0, store) == 1
    second = _state(("default", "My watchlist", ["^FTSE"]), ("wl-a-1", "Tech", ["AAPL", "MSFT"]), active="wl-a-1")
    assert wl.save_watchlists(ALICE, second, 1, store) == 2

    assert wl.load_watchlists(ALICE, store) == {"revision": 2, "state": second.model_dump()}


def test_files_are_named_by_the_email_hash_and_hold_no_email(store, tmp_path: Path) -> None:
    wl.save_watchlists(ALICE, _state(), 0, store)

    [path] = list(tmp_path.iterdir())
    assert path.name == f"{wl.user_key('alice@example.com')}.json"
    assert "alice" not in path.read_text().lower()
    assert not list(tmp_path.glob(".*.tmp")), "the atomic write must not leave its temp file"


def test_users_are_isolated(store) -> None:
    wl.save_watchlists(ALICE, _state(("default", "Alice's", ["AZN.L"])), 0, store)

    assert wl.load_watchlists(BOB, store) == {"revision": 0, "state": None}


def test_stale_revision_conflicts_with_the_current_copy(store) -> None:
    wl.save_watchlists(ALICE, _state(("default", "Phone", ["BP.L"])), 0, store)

    with pytest.raises(wl.WatchlistsConflict) as excinfo:
        wl.save_watchlists(ALICE, _state(("default", "Laptop", ["SHEL.L"])), 0, store)
    assert excinfo.value.current["revision"] == 1
    assert excinfo.value.current["state"]["lists"][0]["name"] == "Phone"


@pytest.mark.parametrize(
    "raw",
    [b"not json", b"[]", b'{"revision": 0}', b'{"revision": 1, "activeId": "x", "lists": []}'],
)
def test_a_damaged_document_is_unavailable_and_never_overwritten(store, tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / f"{wl.user_key(ALICE)}.json"
    path.write_bytes(raw)

    with pytest.raises(wl.WatchlistsUnavailable):
        wl.load_watchlists(ALICE, store)
    with pytest.raises(wl.WatchlistsUnavailable):
        wl.save_watchlists(ALICE, _state(), 0, store)
    assert path.read_bytes() == raw


def test_state_trims_names_and_symbols() -> None:
    state = _state(("default", "  Mine  ", [" VOD.L ", "^GSPC"]))
    assert state.lists[0].name == "Mine"
    assert state.lists[0].symbols == ["VOD.L", "^GSPC"]


@pytest.mark.parametrize(
    "lists, active",
    [
        ([], "default"),
        ([{"id": "a", "name": "One", "symbols": []}], "missing"),
        ([{"id": "a", "name": "One", "symbols": []}, {"id": "a", "name": "Two", "symbols": []}], "a"),
        ([{"id": "a", "name": "Same", "symbols": []}, {"id": "b", "name": "SAME ", "symbols": []}], "a"),
        ([{"id": "a", "name": "   ", "symbols": []}], "a"),
        ([{"id": "../x", "name": "One", "symbols": []}], "../x"),
        ([{"id": "a", "name": "One", "symbols": ["VOD.L,BP.L"]}], "a"),
        ([{"id": "a", "name": "One", "symbols": ["  "]}], "a"),
        ([{"id": "a", "name": "One", "symbols": [], "extra": 1}], "a"),
    ],
)
def test_state_rejects_invalid_shapes(lists, active) -> None:
    with pytest.raises(ValidationError):
        wl.WatchlistsState.model_validate({"activeId": active, "lists": lists})


def test_state_caps_list_count() -> None:
    lists = [{"id": f"l{i}", "name": f"L{i}", "symbols": []} for i in range(wl.MAX_LISTS + 1)]
    with pytest.raises(ValidationError):
        wl.WatchlistsState.model_validate({"activeId": "l0", "lists": lists})


def test_store_from_uri_and_default(monkeypatch, tmp_path: Path) -> None:
    s3 = wl.store_from_uri("s3://bucket/watchlists")
    assert isinstance(s3, wl.S3WatchlistsStore) and (s3.bucket, s3.prefix) == ("bucket", "watchlists")
    assert wl.store_from_uri(f"file://{tmp_path}").root == tmp_path
    assert wl.store_from_uri(str(tmp_path)).root == tmp_path

    monkeypatch.delenv("WATCHLISTS_STORAGE_URI", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "data-bkt")
    default = wl.get_watchlists_store()
    assert isinstance(default, wl.S3WatchlistsStore) and (default.bucket, default.prefix) == ("data-bkt", "watchlists")

    monkeypatch.delenv("DATA_BUCKET")
    monkeypatch.setattr(wl.config, "data_root", tmp_path)
    assert wl.get_watchlists_store().root == tmp_path / "watchlists"


# --- S3 ---------------------------------------------------------------------


def _s3_store():
    client = boto3.client("s3", region_name="eu-west-2", aws_access_key_id="x", aws_secret_access_key="x")
    return wl.S3WatchlistsStore(bucket="bkt", prefix="watchlists", client=client), Stubber(client)


def _body(doc: dict) -> StreamingBody:
    raw = json.dumps(doc).encode()
    return StreamingBody(io.BytesIO(raw), len(raw))


def _key(email: str) -> str:
    return f"watchlists/{wl.user_key(email)}.json"


def test_s3_missing_key_reads_as_nothing_saved() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    with stub:
        assert wl.load_watchlists(ALICE, store) == {"revision": 0, "state": None}


def test_s3_access_denied_is_unavailable_not_empty() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
    with stub, pytest.raises(wl.WatchlistsUnavailable):
        wl.load_watchlists(ALICE, store)


def test_s3_first_save_requires_the_key_to_be_absent() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_response(
        "put_object",
        {},
        {"Bucket": "bkt", "Key": _key(ALICE), "Body": ANY, "ContentType": "application/json", "IfNoneMatch": "*"},
    )
    with stub:
        assert wl.save_watchlists(ALICE, _state(), 0, store) == 1
    stub.assert_no_pending_responses()


def test_s3_save_is_conditional_on_the_etag_and_a_lost_race_conflicts() -> None:
    store, stub = _s3_store()
    stub.add_response("get_object", {"Body": _body(wl._document(1, _state())), "ETag": '"e1"'})
    stub.add_client_error(
        "put_object",
        service_error_code="PreconditionFailed",
        http_status_code=412,
        expected_params={
            "Bucket": "bkt",
            "Key": _key(ALICE),
            "Body": ANY,
            "ContentType": "application/json",
            "IfMatch": '"e1"',
        },
    )
    winner = wl._document(2, _state(("default", "Other device", ["BP.L"])))
    stub.add_response("get_object", {"Body": _body(winner), "ETag": '"e2"'})
    with stub, pytest.raises(wl.WatchlistsConflict) as excinfo:
        wl.save_watchlists(ALICE, _state(("default", "Mine", ["AZN.L"])), 1, store)
    assert excinfo.value.current["revision"] == 2
    assert excinfo.value.current["state"]["lists"][0]["name"] == "Other device"


def test_s3_write_failure_is_unavailable() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_client_error("put_object", service_error_code="InternalError", http_status_code=500)
    with stub, pytest.raises(wl.WatchlistsUnavailable):
        wl.save_watchlists(ALICE, _state(), 0, store)
