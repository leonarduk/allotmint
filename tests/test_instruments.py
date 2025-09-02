import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.common import instruments


def test_missing_file_returns_empty(monkeypatch, tmp_path):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: missing)
    assert instruments.get_instrument_meta("DOES.NOTEXIST") == {}


def test_invalid_json_returns_empty(monkeypatch, tmp_path, caplog):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: bad)
    with caplog.at_level("WARNING"):
        assert instruments.get_instrument_meta("BAD.JSON") == {}
    assert "Invalid instrument JSON" in caplog.text


def test_unexpected_error_propagates(monkeypatch, tmp_path, caplog):
    path = tmp_path / "ok.json"
    path.write_text("{}")
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: path)

    def boom(fp):
        raise RuntimeError("boom")

    monkeypatch.setattr(instruments.json, "load", boom)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            instruments.get_instrument_meta("ERR.TKR")
    assert "Unexpected error loading" in caplog.text


def test_get_instrument_meta_from_s3(monkeypatch):
    monkeypatch.setenv(instruments.METADATA_BUCKET_ENV, "bucket")
    monkeypatch.setenv(instruments.METADATA_PREFIX_ENV, "meta")
    root = Path("dummy")
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", root)
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: root / "L" / "ABC.json")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            assert Bucket == "bucket"
            assert Key == "meta/L/ABC.json"
            return {"Body": io.BytesIO(b'{"foo": 1}')}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    instruments.get_instrument_meta.cache_clear()
    assert instruments.get_instrument_meta("ABC.L") == {"foo": 1}


def test_save_instrument_meta_uploads_s3(monkeypatch, tmp_path):
    monkeypatch.setenv(instruments.METADATA_BUCKET_ENV, "bucket")
    monkeypatch.setenv(instruments.METADATA_PREFIX_ENV, "meta")
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)

    uploaded: dict = {}

    def fake_client(name):
        assert name == "s3"

        def put_object(Bucket, Key, Body):
            uploaded["Bucket"] = Bucket
            uploaded["Key"] = Key
            uploaded["Body"] = Body

        return SimpleNamespace(put_object=put_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    instruments.save_instrument_meta("ABC.L", {"bar": 2})
    path = tmp_path / "L" / "ABC.json"
    assert path.exists()
    assert json.loads(path.read_text()) == {"bar": 2}
    assert uploaded["Bucket"] == "bucket"
    assert uploaded["Key"] == "meta/L/ABC.json"
    assert json.loads(uploaded["Body"].decode()) == {"bar": 2}
