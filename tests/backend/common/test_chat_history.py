"""Tests for backend.common.chat_history (#8870)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from backend.common import chat_history as ch

ALICE = "Alice@Example.com"
BOB = "bob@example.com"


def _conversation(*contents: str) -> dict:
    nodes = []
    active = {}
    parent = None
    for i, content in enumerate(contents, start=1):
        node_id = str(i)
        nodes.append({"id": node_id, "parentId": parent, "role": "user" if i % 2 else "assistant", "content": content})
        active[parent or "root"] = node_id
        parent = node_id
    return {"nodes": nodes, "active": active, "nextId": len(contents) + 1}


@pytest.fixture
def store(tmp_path: Path) -> ch.FileChatStore:
    return ch.FileChatStore(root=tmp_path)


def test_user_key_hashes_the_normalised_email() -> None:
    assert ch.user_key(ALICE) == ch.user_key("  alice@example.com ")
    assert ch.user_key(ALICE) != ch.user_key(BOB)
    assert "@" not in ch.user_key(ALICE) and len(ch.user_key(ALICE)) == 64


def test_load_without_a_saved_conversation_is_empty_at_revision_zero(store) -> None:
    assert ch.load_conversation(ALICE, store) == {"revision": 0, "conversation": ch.empty_conversation()}


def test_save_then_load_round_trips_and_bumps_the_revision(store) -> None:
    assert ch.save_conversation(ALICE, _conversation("hi", "hello"), 0, store) == 1
    assert ch.save_conversation(ALICE, _conversation("hi", "hello", "more"), 1, store) == 2

    loaded = ch.load_conversation(ALICE, store)
    assert loaded["revision"] == 2
    assert [n["content"] for n in loaded["conversation"]["nodes"]] == ["hi", "hello", "more"]


def test_files_are_named_by_the_email_hash_never_the_email(store, tmp_path: Path) -> None:
    ch.save_conversation(ALICE, _conversation("hi"), 0, store)
    ch.archive_conversation(ALICE, store)

    names = [str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")]
    assert all("alice" not in name.lower() and "@" not in name for name in names)
    assert (tmp_path / ch.user_key(ALICE) / "current.json").is_file()


def test_stale_revision_conflicts_with_the_current_document(store) -> None:
    ch.save_conversation(ALICE, _conversation("from tab 1"), 0, store)

    with pytest.raises(ch.ChatConversationConflict) as excinfo:
        ch.save_conversation(ALICE, _conversation("from tab 2"), 0, store)

    assert excinfo.value.current["revision"] == 1
    assert excinfo.value.current["conversation"]["nodes"][0]["content"] == "from tab 1"
    assert ch.load_conversation(ALICE, store)["revision"] == 1


def test_users_are_isolated(store) -> None:
    ch.save_conversation(ALICE, _conversation("alice's holdings"), 0, store)

    assert ch.load_conversation(BOB, store)["revision"] == 0
    # Bob saving at revision 0 creates his own document; Alice's is untouched.
    ch.save_conversation(BOB, _conversation("bob"), 0, store)
    assert ch.load_conversation(ALICE, store)["conversation"]["nodes"][0]["content"] == "alice's holdings"
    ch.delete_history(BOB, store)
    assert ch.load_conversation(ALICE, store)["revision"] == 1


def test_archive_keeps_the_old_conversation_and_starts_an_empty_one(store, tmp_path: Path) -> None:
    ch.save_conversation(ALICE, _conversation("keep me"), 0, store)

    assert ch.archive_conversation(ALICE, store) == {"revision": 2, "archived": True}

    assert ch.load_conversation(ALICE, store) == {"revision": 2, "conversation": ch.empty_conversation()}
    archived = list((tmp_path / ch.user_key(ALICE) / "archive").iterdir())
    assert len(archived) == 1
    assert json.loads(archived[0].read_text())["conversation"]["nodes"][0]["content"] == "keep me"


def test_archive_of_an_empty_conversation_writes_nothing(store, tmp_path: Path) -> None:
    assert ch.archive_conversation(ALICE, store) == {"revision": 0, "archived": False}
    assert not any(tmp_path.iterdir())


def test_archive_retries_when_a_write_lands_in_between(store, monkeypatch) -> None:
    ch.save_conversation(ALICE, _conversation("v1"), 0, store)
    real_write = store.write
    calls = {"n": 0}

    def racing_write(key, data, *, expect_tag):
        calls["n"] += 1
        if calls["n"] == 1:
            # Another device saves between the archive's read and its write.
            real_write(key, json.dumps(ch._document(2, _conversation("v2"))).encode(), expect_tag=expect_tag)
        return real_write(key, data, expect_tag=expect_tag)

    monkeypatch.setattr(store, "write", racing_write)

    assert ch.archive_conversation(ALICE, store) == {"revision": 3, "archived": True}
    archived = sorted((store.root / ch.user_key(ALICE) / "archive").iterdir())
    assert [json.loads(p.read_text())["conversation"]["nodes"][0]["content"] for p in archived] == ["v1", "v2"]


def test_archive_retry_of_the_same_revision_does_not_duplicate_it(store, monkeypatch) -> None:
    ch.save_conversation(ALICE, _conversation("v1"), 0, store)
    real_write = store.write
    calls = {"n": 0}

    def flaky_write(key, data, *, expect_tag):
        calls["n"] += 1
        if calls["n"] == 1:
            # A conditional write that fails without anything having changed.
            raise ch._PreconditionFailed()
        return real_write(key, data, expect_tag=expect_tag)

    monkeypatch.setattr(store, "write", flaky_write)

    assert ch.archive_conversation(ALICE, store) == {"revision": 2, "archived": True}
    archived = list((store.root / ch.user_key(ALICE) / "archive").iterdir())
    assert [p.name for p in archived] == ["r00000001.json"]


@pytest.mark.parametrize("bad", [b'{"revision": -1}', b'{"revision": true}', b'{"revision": "3"}', b"[]"])
def test_malformed_stored_revision_is_an_error(store, tmp_path: Path, bad: bytes) -> None:
    path = tmp_path / ch.user_key(ALICE) / "current.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(bad)

    with pytest.raises(ch.ChatHistoryUnavailable):
        ch.load_conversation(ALICE, store)


def test_delete_history_removes_current_and_archives(store, tmp_path: Path) -> None:
    ch.save_conversation(ALICE, _conversation("one"), 0, store)
    ch.archive_conversation(ALICE, store)
    ch.save_conversation(ALICE, _conversation("two"), 2, store)

    assert ch.delete_history(ALICE, store) == 2
    assert not (tmp_path / ch.user_key(ALICE)).exists()
    assert ch.load_conversation(ALICE, store)["revision"] == 0
    assert ch.delete_history(ALICE, store) == 0


def test_corrupt_stored_document_is_an_error_not_an_empty_conversation(store, tmp_path: Path) -> None:
    path = tmp_path / ch.user_key(ALICE) / "current.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")

    with pytest.raises(ch.ChatHistoryUnavailable):
        ch.load_conversation(ALICE, store)
    # A save must not overwrite what could not be read.
    with pytest.raises(ch.ChatHistoryUnavailable):
        ch.save_conversation(ALICE, _conversation("x"), 0, store)
    assert path.read_text() == "{not json"


def test_store_from_uri_and_default(monkeypatch, tmp_path: Path) -> None:
    s3 = ch.store_from_uri("s3://bucket/chat/")
    assert isinstance(s3, ch.S3ChatStore) and (s3.bucket, s3.prefix) == ("bucket", "chat")
    assert ch.store_from_uri(f"file://{tmp_path}") == ch.FileChatStore(root=tmp_path)
    assert ch.store_from_uri(str(tmp_path)) == ch.FileChatStore(root=tmp_path)
    with pytest.raises(ValueError):
        ch.store_from_uri("ssm://nope")

    monkeypatch.setenv("CHAT_HISTORY_STORAGE_URI", f"file://{tmp_path}/x")
    assert ch.get_chat_store() == ch.FileChatStore(root=tmp_path / "x")
    monkeypatch.delenv("CHAT_HISTORY_STORAGE_URI")
    monkeypatch.setattr(ch.config, "data_root", tmp_path)
    assert ch.get_chat_store() == ch.FileChatStore(root=tmp_path / "chat")


# --- S3 ---------------------------------------------------------------------


def _s3_store():
    client = boto3.client("s3", region_name="eu-west-2", aws_access_key_id="x", aws_secret_access_key="x")
    return ch.S3ChatStore(bucket="bkt", prefix="chat", client=client), Stubber(client)


def _body(doc: dict) -> StreamingBody:
    raw = json.dumps(doc).encode()
    return StreamingBody(io.BytesIO(raw), len(raw))


def _current_key(email: str) -> str:
    return f"chat/{ch.user_key(email)}/current.json"


def test_s3_missing_key_reads_as_revision_zero() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    with stub:
        assert ch.load_conversation(ALICE, store)["revision"] == 0


def test_s3_access_denied_is_unavailable_not_empty() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
    with stub, pytest.raises(ch.ChatHistoryUnavailable):
        ch.load_conversation(ALICE, store)


def test_s3_first_save_requires_the_key_to_be_absent() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_response(
        "put_object",
        {},
        {
            "Bucket": "bkt",
            "Key": _current_key(ALICE),
            "Body": ANY,
            "ContentType": "application/json",
            "IfNoneMatch": "*",
        },
    )
    with stub:
        assert ch.save_conversation(ALICE, _conversation("hi"), 0, store) == 1
    stub.assert_no_pending_responses()


def test_s3_save_is_conditional_on_the_etag_and_a_lost_race_conflicts() -> None:
    store, stub = _s3_store()
    stored = ch._document(1, _conversation("v1"))
    stub.add_response("get_object", {"Body": _body(stored), "ETag": '"e1"'})
    stub.add_client_error(
        "put_object",
        service_error_code="PreconditionFailed",
        http_status_code=412,
        expected_params={
            "Bucket": "bkt",
            "Key": _current_key(ALICE),
            "Body": ANY,
            "ContentType": "application/json",
            "IfMatch": '"e1"',
        },
    )
    winner = ch._document(2, _conversation("other device"))
    stub.add_response("get_object", {"Body": _body(winner), "ETag": '"e2"'})
    with stub, pytest.raises(ch.ChatConversationConflict) as excinfo:
        ch.save_conversation(ALICE, _conversation("mine"), 1, store)
    assert excinfo.value.current["revision"] == 2


def test_s3_delete_history_deletes_every_object_under_the_user_prefix() -> None:
    store, stub = _s3_store()
    prefix = f"chat/{ch.user_key(ALICE)}/"
    keys = [prefix + "current.json", prefix + "archive/a.json"]
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": k} for k in keys], "IsTruncated": False},
        {"Bucket": "bkt", "Prefix": prefix},
    )
    stub.add_response(
        "delete_objects",
        {},
        {"Bucket": "bkt", "Delete": {"Objects": [{"Key": k} for k in keys], "Quiet": True}},
    )
    with stub:
        assert ch.delete_history(ALICE, store) == 2
    stub.assert_no_pending_responses()


def test_s3_write_failure_is_unavailable() -> None:
    store, stub = _s3_store()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_client_error("put_object", service_error_code="InternalError", http_status_code=500)
    with stub, pytest.raises(ch.ChatHistoryUnavailable):
        ch.save_conversation(ALICE, _conversation("hi"), 0, store)
