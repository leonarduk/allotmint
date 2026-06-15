"""Tests for the pluggable writable accounts store (issue #4275)."""

from __future__ import annotations

import io
import json

import pytest

from backend.common.accounts_store import (
    WRITABLE_ACCOUNTS_PREFIX,
    LocalAccountsStore,
    S3AccountsStore,
)

# ---------------------------------------------------------------------------
# LocalAccountsStore
# ---------------------------------------------------------------------------


def test_local_store_edit_creates_and_updates(tmp_path):
    store = LocalAccountsStore(root=tmp_path)

    with store.edit_document("alice", "isa.json", default={}) as data:
        data["holdings"] = [{"ticker": "AAA", "value_gbp": 100}]

    saved = json.loads((tmp_path / "alice" / "isa.json").read_text())
    assert saved["holdings"] == [{"ticker": "AAA", "value_gbp": 100}]

    with store.edit_document("alice", "isa.json", default={}) as data:
        data["holdings"].append({"ticker": "BBB", "value_gbp": 50})

    saved = json.loads((tmp_path / "alice" / "isa.json").read_text())
    assert len(saved["holdings"]) == 2


def test_local_store_edit_discards_new_file_on_error(tmp_path):
    store = LocalAccountsStore(root=tmp_path)
    file_path = tmp_path / "alice" / "isa.json"

    with pytest.raises(RuntimeError):
        with store.edit_document("alice", "isa.json", default={}) as data:
            data["holdings"] = [{"ticker": "AAA"}]
            raise RuntimeError("boom")

    assert not file_path.exists()


def test_local_store_coerces_non_dict_to_default(tmp_path):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text("[1, 2, 3]")
    store = LocalAccountsStore(root=tmp_path)

    with store.edit_document("alice", "isa.json", default={"holdings": []}) as data:
        assert data == {"holdings": []}
        data["holdings"].append({"ticker": "AAA"})

    saved = json.loads((owner_dir / "isa.json").read_text())
    assert saved["holdings"] == [{"ticker": "AAA"}]


def test_local_store_ensure_owner_scaffolds_person(tmp_path):
    store = LocalAccountsStore(root=tmp_path)
    store.ensure_owner("alice")
    person = json.loads((tmp_path / "alice" / "person.json").read_text())
    assert person["owner"] == "alice"


def test_local_store_global_is_read_only(tmp_path):
    store = LocalAccountsStore(root=tmp_path, is_global=True)
    # ensure_owner must not scaffold against a read-only/global root.
    store.ensure_owner("alice")
    assert not (tmp_path / "alice").exists()


def test_local_store_none_root_lists_empty():
    store = LocalAccountsStore(root=None)
    assert store.list_owner_files("alice") == []
    assert store.owner_exists("alice") is False
    assert list(store.iter_transaction_documents()) == []


# ---------------------------------------------------------------------------
# S3AccountsStore (in-memory fake S3 client)
# ---------------------------------------------------------------------------


class _FakeS3:
    """Minimal in-memory stand-in for the boto3 S3 client surface used here."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_object(self, Bucket: str, Key: str):  # noqa: N803 - boto3 kwarg names
        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject"
            )
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_kwargs):  # noqa: N803
        self.objects[Key] = Body

    def list_objects_v2(self, Bucket: str, Prefix: str, **_kwargs):  # noqa: N803
        contents = [
            {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


@pytest.fixture
def s3_store():
    fake = _FakeS3()
    store = S3AccountsStore(bucket="data-bucket", client=fake)
    return store, fake


def test_s3_store_write_uses_writable_prefix(s3_store):
    store, fake = s3_store
    with store.edit_document("alice", "isa.json", default={"holdings": []}) as data:
        data["holdings"].append({"ticker": "AAA", "value_gbp": 100})

    expected_key = f"{WRITABLE_ACCOUNTS_PREFIX}/alice/isa.json"
    assert expected_key in fake.objects
    # Never write under the read-only shared demo prefix.
    assert not any(k.startswith("accounts/") for k in fake.objects)

    stored = json.loads(fake.objects[expected_key].decode("utf-8"))
    assert stored["holdings"] == [{"ticker": "AAA", "value_gbp": 100}]


def test_s3_store_read_missing_returns_none(s3_store):
    store, _ = s3_store
    assert store.read_document("ghost", "isa.json") is None


def test_s3_store_edit_reads_existing_then_writes(s3_store):
    store, fake = s3_store
    with store.edit_document("alice", "isa.json", default={"holdings": []}) as data:
        data["holdings"].append({"ticker": "AAA"})
    with store.edit_document("alice", "isa.json", default={"holdings": []}) as data:
        assert data["holdings"] == [{"ticker": "AAA"}]
        data["holdings"].append({"ticker": "BBB"})

    stored = json.loads(
        fake.objects[f"{WRITABLE_ACCOUNTS_PREFIX}/alice/isa.json"].decode("utf-8")
    )
    assert [h["ticker"] for h in stored["holdings"]] == ["AAA", "BBB"]


def test_s3_store_list_and_iter(s3_store):
    store, _ = s3_store
    with store.edit_document("alice", "isa.json", default={}) as data:
        data["holdings"] = []
    with store.edit_document(
        "alice", "isa_transactions.json", default={}
    ) as data:
        data["account_type"] = "isa"
        data["transactions"] = [{"ticker": "AAA"}]

    assert set(store.list_owner_files("alice")) == {
        "isa.json",
        "isa_transactions.json",
    }
    assert store.owner_exists("alice") is True
    assert store.owner_exists("bob") is False

    docs = list(store.iter_transaction_documents())
    assert len(docs) == 1
    owner, account_raw, data = docs[0]
    assert owner == "alice"
    assert account_raw == "isa"
    assert data["transactions"] == [{"ticker": "AAA"}]


def test_s3_store_ensure_owner_idempotent(s3_store):
    store, fake = s3_store
    store.ensure_owner("alice")
    assert f"{WRITABLE_ACCOUNTS_PREFIX}/alice/person.json" in fake.objects
    # Second call must not overwrite / error.
    store.ensure_owner("alice")
    person = json.loads(
        fake.objects[f"{WRITABLE_ACCOUNTS_PREFIX}/alice/person.json"].decode("utf-8")
    )
    assert person["owner"] == "alice"
