"""Where saved plan briefs live (#10475): PLAN_BRIEFS_URI, else <data_root>/plan_briefs."""

from __future__ import annotations

import pytest

from backend.common.storage import FileJSONStorage, S3JSONStorage
from backend.plan_brief import store


def test_s3_uri_is_used_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAN_BRIEFS_URI", "s3://data-bucket/plan_briefs")
    storage = store._storage("alex", tmp_path)
    assert isinstance(storage, S3JSONStorage)
    assert (storage.bucket, storage.key) == ("data-bucket", "plan_briefs/alex.json")


def test_s3_round_trip_through_the_bucket(monkeypatch, tmp_path):
    """The API Lambda reads what the scheduled Lambda wrote: same bucket and key, newest first."""
    objects: dict[tuple[str, str], bytes] = {}

    class FakeS3:
        def get_object(self, Bucket, Key):  # noqa: N803
            import io

            from botocore.exceptions import ClientError

            if (Bucket, Key) not in objects:
                raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
            return {"Body": io.BytesIO(objects[(Bucket, Key)])}

        def put_object(self, Bucket, Key, Body):  # noqa: N803
            objects[(Bucket, Key)] = Body

    monkeypatch.setenv("PLAN_BRIEFS_URI", "s3://data-bucket/plan_briefs")
    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: FakeS3())

    store.save_brief("alex", {"id": "a", "as_of": "2026-09-01"}, tmp_path)
    store.save_brief("alex", {"id": "b", "as_of": "2026-10-01"}, tmp_path)

    assert list(objects) == [("data-bucket", "plan_briefs/alex.json")]
    assert [b["id"] for b in store.list_briefs("alex", tmp_path)] == ["b", "a"]
    assert not (tmp_path / "plan_briefs").exists()


def test_local_default_is_beside_plans(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAN_BRIEFS_URI", raising=False)
    storage = store._storage("alex", tmp_path)
    assert isinstance(storage, FileJSONStorage)
    assert storage.path == tmp_path / "plan_briefs" / "alex.json"


def test_history_is_capped(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAN_BRIEFS_URI", raising=False)
    for i in range(store.MAX_BRIEFS + 3):
        store.save_brief("alex", {"id": str(i), "as_of": "2026-10-01"}, tmp_path)
    briefs = store.list_briefs("alex", tmp_path)
    assert len(briefs) == store.MAX_BRIEFS and briefs[0]["id"] == str(store.MAX_BRIEFS + 2)


@pytest.mark.parametrize("owner", ["../evil", "", "a/b"])
def test_invalid_owner_is_rejected(owner, tmp_path):
    with pytest.raises(ValueError):
        store._storage(owner, tmp_path)
