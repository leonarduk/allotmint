import os
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from backend.common.storage import (
    FileJSONStorage,
    ParameterStoreJSONStorage,
    S3JSONStorage,
    get_storage,
)


def test_get_storage_file_relative(tmp_path):
    # Relative file URI should resolve to FileJSONStorage with absolute path
    uri = "file://relative/path.json"
    storage = get_storage(uri)
    assert isinstance(storage, FileJSONStorage)
    assert storage.path.is_absolute()
    # Path should end with the given relative path
    assert str(storage.path).endswith(os.path.join("relative", "path.json"))


def test_get_storage_file_absolute(tmp_path):
    file_path = tmp_path / "file.json"
    uri = f"file://{file_path}"
    storage = get_storage(uri)
    assert isinstance(storage, FileJSONStorage)
    assert storage.path == file_path


def test_get_storage_other_schemes():
    s3_storage = get_storage("s3://bucket/key.json")
    assert isinstance(s3_storage, S3JSONStorage)
    assert s3_storage.bucket == "bucket"
    assert s3_storage.key == "key.json"

    ssm_storage = get_storage("ssm://parameter-name")
    assert isinstance(ssm_storage, ParameterStoreJSONStorage)
    assert ssm_storage.name == "parameter-name"


def test_get_storage_unknown_scheme():
    with pytest.raises(ValueError):
        get_storage("ftp://example.com/resource")


def _client_error(operation):
    return ClientError(
        {"Error": {"Code": "TestException", "Message": "boom"}}, operation
    )


def test_s3_load_client_error(monkeypatch):
    storage = get_storage("s3://bucket/key")
    client = Mock()
    client.get_object.side_effect = _client_error("GetObject")
    monkeypatch.setattr(storage, "_client", lambda: client)
    assert storage.load() == {}


def test_ssm_load_client_error(monkeypatch):
    storage = get_storage("ssm://param")
    client = Mock()
    client.get_parameter.side_effect = _client_error("GetParameter")
    monkeypatch.setattr(storage, "_client", lambda: client)
    assert storage.load() == {}
