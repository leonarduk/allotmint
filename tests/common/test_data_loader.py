import json
import sys
from types import SimpleNamespace

import backend.common.data_loader as dl


def test_load_person_meta_falls_back_to_local(tmp_path, monkeypatch):
    owner = "alice"
    owner_dir = tmp_path / owner
    owner_dir.mkdir()
    (owner_dir / "person.json").write_text(
        json.dumps({"dob": "1970-01-01", "viewers": ["bob"]}),
        encoding="utf-8",
    )

    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def raising_client(name):
        raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=raising_client))

    meta = dl.load_person_meta(owner, data_root=tmp_path)
    assert meta["dob"] == "1970-01-01"
    assert meta["viewers"] == ["bob"]
