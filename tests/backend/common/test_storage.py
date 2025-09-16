import json
import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from backend.common.storage import (
    FileJSONStorage,
    ParameterStoreJSONStorage,
    S3JSONStorage,
    get_storage,
)


def make_client_error(operation: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": "TestException", "Message": "boom"}},
        operation_name=operation,
    )


def test_file_storage_load_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    storage = FileJSONStorage(path=path)

    result = storage.load()

    assert result == {}
    assert not path.exists()


def test_file_storage_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "data" / "storage.json"
    storage = FileJSONStorage(path=path)
    payload = {"key": "value", "numbers": [1, 2, 3]}

    storage.save(payload)

    assert path.exists()
    assert json.loads(path.read_text()) == payload
    assert storage.load() == payload


def test_file_storage_invalid_json_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{not-valid-json}")
    storage = FileJSONStorage(path=path)

    with caplog.at_level(logging.WARNING):
        result = storage.load()

    assert result == {}
    assert "Failed to read" in caplog.text
    assert str(path) in caplog.text


def test_s3_storage_load_and_save() -> None:
    client = Mock()
    body = Mock()
    expected = {"answer": 42}
    body.read.return_value = json.dumps(expected).encode("utf-8")
    client.get_object.return_value = {"Body": body}
    storage = S3JSONStorage(bucket="bucket", key="path/file.json", client=client)

    result = storage.load()

    assert result == expected
    client.get_object.assert_called_once_with(Bucket="bucket", Key="path/file.json")

    new_payload = {"foo": "bar"}
    storage.save(new_payload)

    client.put_object.assert_called_once()
    _args, kwargs = client.put_object.call_args
    assert kwargs["Bucket"] == "bucket"
    assert kwargs["Key"] == "path/file.json"
    assert json.loads(kwargs["Body"].decode("utf-8")) == new_payload


def test_s3_storage_load_error_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    client = Mock()
    client.get_object.side_effect = make_client_error("GetObject")
    storage = S3JSONStorage(bucket="bucket", key="path/file.json", client=client)

    with caplog.at_level(logging.WARNING):
        result = storage.load()

    assert result == {}
    assert "S3 load failed" in caplog.text
    assert "bucket/path/file.json" in caplog.text


def test_parameter_store_load_and_save() -> None:
    client = Mock()
    expected = {"value": 1}
    client.get_parameter.return_value = {
        "Parameter": {"Value": json.dumps(expected)}
    }
    storage = ParameterStoreJSONStorage(name="/param/name", client=client)

    result = storage.load()

    assert result == expected
    client.get_parameter.assert_called_once_with(Name="/param/name", WithDecryption=True)

    payload = {"next": "value"}
    storage.save(payload)

    client.put_parameter.assert_called_once_with(
        Name="/param/name",
        Value=json.dumps(payload),
        Type="String",
        Overwrite=True,
    )


def test_parameter_store_load_error_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    client = Mock()
    client.get_parameter.side_effect = make_client_error("GetParameter")
    storage = ParameterStoreJSONStorage(name="/param/name", client=client)

    with caplog.at_level(logging.WARNING):
        result = storage.load()

    assert result == {}
    assert "Parameter Store load failed" in caplog.text
    assert "/param/name" in caplog.text


@pytest.mark.parametrize(
    "uri, expected_type, attrs",
    [
        ("file:///tmp/config.json", FileJSONStorage, {"path": Path("/tmp/config.json")}),
        ("s3://bucket/key.json", S3JSONStorage, {"bucket": "bucket", "key": "key.json"}),
        ("ssm://parameter/name", ParameterStoreJSONStorage, {"name": "parameter/name"}),
    ],
)
def test_get_storage_supported_schemes(uri: str, expected_type: type, attrs: dict) -> None:
    storage = get_storage(uri)
    assert isinstance(storage, expected_type)
    for attr, value in attrs.items():
        assert getattr(storage, attr) == value


def test_get_storage_unsupported_scheme() -> None:
    with pytest.raises(ValueError):
        get_storage("ftp://example.com/resource")
