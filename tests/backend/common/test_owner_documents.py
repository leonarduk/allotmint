"""Per-owner JSON documents on disk or in S3 (#11159)."""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError

from backend.common.owner_documents import OwnerDocumentStore
from backend.common.storage import S3JSONStorage, list_s3_json_stems
from tests.backend.fake_s3 import FakeS3

ENV = "TEST_OWNER_DOCS_URI"


def _store():
    return OwnerDocumentStore(uri_env=ENV, local_dir=lambda root: root / "docs")


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setenv(ENV, "s3://data-bucket/docs")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: fake)
    return fake


def test_local_round_trip_is_atomic_and_pretty(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV, raising=False)
    store = _store()
    assert store.read("alex", tmp_path) is None
    path = store.write("alex", {"owner": "alex"}, tmp_path)
    assert path == tmp_path / "docs" / "alex.json"
    assert path.read_text(encoding="utf-8") == '{\n  "owner": "alex"\n}\n'
    assert store.read("alex", tmp_path) == {"owner": "alex"}
    assert store.owners(tmp_path) == {"alex"}
    assert not list((tmp_path / "docs").glob("*.tmp"))


def test_local_owners_without_a_directory(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV, raising=False)
    assert _store().owners(tmp_path) == set()


def test_s3_round_trip_writes_nothing_locally(s3, tmp_path):
    store = _store()
    assert store.read("alex", tmp_path) is None
    assert store.write("alex", {"owner": "alex"}, tmp_path) is None
    store.write("bob", {"owner": "bob"}, tmp_path)
    assert json.loads(s3.objects[("data-bucket", "docs/alex.json")]) == {"owner": "alex"}
    assert store.read("alex", tmp_path) == {"owner": "alex"}
    assert store.owners(tmp_path) == {"alex", "bob"}
    assert not (tmp_path / "docs").exists()


def test_s3_read_error_raises_instead_of_reading_as_empty(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "s3://data-bucket/docs")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: FakeS3(fail_with="AccessDenied"))
    with pytest.raises(ClientError):
        _store().read("alex", tmp_path)


@pytest.mark.parametrize("uri", ["/some/dir", "file:///tmp/docs", "s3://"])
def test_non_s3_uri_is_rejected(monkeypatch, tmp_path, uri):
    monkeypatch.setenv(ENV, uri)
    with pytest.raises(ValueError, match=ENV):
        _store().read("alex", tmp_path)


def test_list_stems_ignores_nested_and_non_json_keys():
    fake = FakeS3()
    keys = ("docs/alex.json", "docs/bob.json", "docs/sub/carol.json", "docs/notes.txt", "docs/.json", "other/x.json")
    for key in keys:
        fake.objects[("b", key)] = b"{}"
    assert list_s3_json_stems("b", "docs", client=fake) == ["alex", "bob"]


def test_load_existing_returns_none_only_for_a_missing_key():
    fake = FakeS3()
    storage = S3JSONStorage(bucket="b", key="k.json", client=fake)
    assert storage.load_existing() is None
    storage.save({"a": 1})
    assert storage.load_existing() == {"a": 1}
    with pytest.raises(ClientError):
        S3JSONStorage(bucket="b", key="k.json", client=FakeS3(fail_with="SlowDown")).load_existing()
