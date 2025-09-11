import json
import sys
import types
from datetime import datetime, timezone

from backend.common import portfolio_utils as pu


def test_load_snapshot_bad_json(tmp_path, monkeypatch, caplog):
    path = tmp_path / "latest_prices.json"
    path.write_text("{bad json")
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)
    with caplog.at_level("ERROR"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert "Failed to parse snapshot" in caplog.text


def test_load_snapshot_no_path(monkeypatch, caplog):
    monkeypatch.setattr(pu.config, "prices_json", None)
    monkeypatch.setattr(pu, "_PRICES_PATH", None)
    with caplog.at_level("INFO"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert "Price snapshot path not configured; skipping load" in caplog.text


def test_load_snapshot_aws_s3_success(monkeypatch):
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = {"ABC": {"price": 1}}

    class FakeBody:
        def read(self):
            return json.dumps(payload).encode("utf-8")

    class FakeS3:
        def get_object(self, Bucket, Key):  # noqa: N802
            return {"Body": FakeBody(), "LastModified": ts}

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeS3())
    fake_exc = types.SimpleNamespace(BotoCoreError=Exception, ClientError=Exception)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", None)
    monkeypatch.setattr(pu, "_PRICES_PATH", None)

    data, returned_ts = pu._load_snapshot()
    assert data == payload
    assert returned_ts == ts


def test_load_snapshot_aws_failure_uses_local(tmp_path, monkeypatch, caplog):
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


def test_load_snapshot_aws_missing_env_uses_local(tmp_path, monkeypatch, caplog):
    payload = {"FOO": {"price": 5}}
    path = tmp_path / "latest_prices.json"
    path.write_text(json.dumps(payload))

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.delenv(pu.DATA_BUCKET_ENV, raising=False)
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)

    with caplog.at_level("ERROR"):
        data, ts = pu._load_snapshot()
    assert data == payload
    assert ts == datetime.fromtimestamp(path.stat().st_mtime)
    assert "Missing" in caplog.text


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
