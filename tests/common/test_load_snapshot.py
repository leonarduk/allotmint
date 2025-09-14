import json
import sys
from datetime import datetime
import types

import pytest

from backend.common import portfolio_utils as pu


def test_load_snapshot_missing_local_file(tmp_path, monkeypatch, caplog):
    path = tmp_path / "missing.json"
    monkeypatch.setattr(pu.config, "app_env", "local")
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)

    with caplog.at_level("WARNING"):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    assert "Price snapshot not found" in caplog.text


def test_load_snapshot_aws_failure_falls_back_to_local(tmp_path, monkeypatch, caplog):
    payload = {"XYZ": {"price": 2}}
    path = tmp_path / "latest_prices.json"
    path.write_text(json.dumps(payload))

    class ClientError(Exception):
        pass

    class FakeS3:
        def get_object(self, Bucket, Key):  # noqa: N802
            raise ClientError("boom")

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeS3())
    fake_exc = types.SimpleNamespace(BotoCoreError=Exception, ClientError=ClientError)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)

    with caplog.at_level("ERROR"):
        data, returned_ts = pu._load_snapshot()

    assert data == payload
    assert returned_ts == datetime.fromtimestamp(path.stat().st_mtime)
    assert "Failed to fetch price snapshot" in caplog.text
