from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from backend.config import config
from backend.routes import data_explorer


def test_list_directory_root(monkeypatch, tmp_path):
    (tmp_path / "timeseries").mkdir()
    (tmp_path / "accounts.json").write_text("{}")

    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = data_explorer.list_directory("")

    assert result["path"] == ""
    names = [(e["name"], e["type"]) for e in result["entries"]]
    assert names == [("timeseries", "dir"), ("accounts.json", "file")]
    file_entry = next(e for e in result["entries"] if e["name"] == "accounts.json")
    assert file_entry["size"] == 2
    assert file_entry["path"] == "accounts.json"


def test_list_directory_subdir(monkeypatch, tmp_path):
    sub = tmp_path / "timeseries" / "meta"
    sub.mkdir(parents=True)
    (sub / "ABC_L.parquet").write_bytes(b"\x00\x01")

    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = data_explorer.list_directory("timeseries/meta")

    assert result["path"] == "timeseries/meta"
    assert result["entries"][0]["path"] == "timeseries/meta/ABC_L.parquet"


def test_list_directory_excludes_git_and_idea_dirs(monkeypatch, tmp_path):
    (tmp_path / "timeseries").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"\x00\x01")
    (tmp_path / ".idea").mkdir()
    (tmp_path / ".idea" / "workspace.xml").write_text("<xml/>")
    (tmp_path / "accounts.json").write_text("{}")

    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = data_explorer.list_directory("")

    names = [e["name"] for e in result["entries"]]
    assert ".git" not in names
    assert ".idea" not in names
    assert set(names) == {"timeseries", "accounts.json"}


def test_list_directory_missing_path_404(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.list_directory("does-not-exist")
    assert exc.value.status_code == 404


def test_list_directory_rejects_file_path(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.list_directory("a.txt")
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "traversal",
    [
        "../",
        "../../etc/passwd",
        "/etc/passwd",
        "timeseries/../../etc",
    ],
)
def test_list_directory_rejects_traversal(monkeypatch, tmp_path, traversal):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.list_directory(traversal)
    assert exc.value.status_code == 400


def test_list_directory_aws_missing_bucket_501(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    with pytest.raises(HTTPException) as exc:
        data_explorer.list_directory("")
    assert exc.value.status_code == 501


def test_list_directory_aws_lists_dirs_and_files(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.list_objects_v2.return_value = {
        "CommonPrefixes": [{"Prefix": "timeseries/"}],
        "Contents": [
            {
                "Key": "accounts.json",
                "Size": 2,
                "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ],
        "IsTruncated": False,
    }

    with patch("boto3.client", return_value=mock_client):
        result = data_explorer.list_directory("")

    assert result["path"] == ""
    names = [(e["name"], e["type"]) for e in result["entries"]]
    assert names == [("timeseries", "dir"), ("accounts.json", "file")]
    file_entry = next(e for e in result["entries"] if e["name"] == "accounts.json")
    assert file_entry["size"] == 2
    assert file_entry["path"] == "accounts.json"
    mock_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", Prefix="", Delimiter="/")


def test_list_directory_aws_subdir_uses_prefixed_key(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.list_objects_v2.return_value = {
        "CommonPrefixes": [],
        "Contents": [
            {
                "Key": "timeseries/meta/ABC_L.parquet",
                "Size": 10,
                "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ],
        "IsTruncated": False,
    }

    with patch("boto3.client", return_value=mock_client):
        result = data_explorer.list_directory("timeseries/meta")

    assert result["path"] == "timeseries/meta"
    assert result["entries"][0]["path"] == "timeseries/meta/ABC_L.parquet"
    mock_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", Prefix="timeseries/meta/", Delimiter="/")


def test_list_directory_aws_paginates(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.list_objects_v2.side_effect = [
        {
            "CommonPrefixes": [],
            "Contents": [
                {
                    "Key": "a.json",
                    "Size": 1,
                    "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
                }
            ],
            "IsTruncated": True,
            "NextContinuationToken": "token-1",
        },
        {
            "CommonPrefixes": [],
            "Contents": [
                {
                    "Key": "b.json",
                    "Size": 2,
                    "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
                }
            ],
            "IsTruncated": False,
        },
    ]

    with patch("boto3.client", return_value=mock_client):
        result = data_explorer.list_directory("")

    names = [e["name"] for e in result["entries"]]
    assert names == ["a.json", "b.json"]
    assert mock_client.list_objects_v2.call_count == 2
    second_call_kwargs = mock_client.list_objects_v2.call_args_list[1].kwargs
    assert second_call_kwargs["ContinuationToken"] == "token-1"


def test_list_directory_aws_empty_subdir_404(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.list_objects_v2.return_value = {
        "CommonPrefixes": [],
        "Contents": [],
        "IsTruncated": False,
    }

    with patch("boto3.client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc:
            data_explorer.list_directory("does-not-exist")
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    "traversal",
    [
        "../",
        "../../etc/passwd",
        "/etc/passwd",
        "timeseries/../../etc",
    ],
)
def test_list_directory_aws_rejects_traversal(monkeypatch, traversal):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    with pytest.raises(HTTPException) as exc:
        data_explorer.list_directory(traversal)
    assert exc.value.status_code == 400


def test_list_directory_aws_list_failure_502(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.list_objects_v2.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListObjectsV2"
    )

    with patch("boto3.client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc:
            data_explorer.list_directory("")
    assert exc.value.status_code == 502


def test_read_file_aws_preview(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.head_object.return_value = {
        "ContentLength": 11,
        "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
    }
    mock_client.get_object.return_value = {"Body": MagicMock(read=lambda: b"hello world")}

    with patch("boto3.client", return_value=mock_client):
        result = data_explorer.read_file("notes.txt")

    assert result["content"] == "hello world"
    assert result["truncated"] is False
    assert result["path"] == "notes.txt"
    mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="notes.txt")


def test_read_file_aws_truncates_large_files(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    big_content = "x" * (data_explorer.MAX_PREVIEW_BYTES + 100)
    mock_client = MagicMock()
    mock_client.head_object.return_value = {
        "ContentLength": len(big_content),
        "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
    }
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: big_content[: data_explorer.MAX_PREVIEW_BYTES].encode("utf-8"))
    }

    with patch("boto3.client", return_value=mock_client):
        result = data_explorer.read_file("big.log")

    assert result["truncated"] is True
    assert len(result["content"]) == data_explorer.MAX_PREVIEW_BYTES
    range_header = f"bytes=0-{data_explorer.MAX_PREVIEW_BYTES - 1}"
    mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="big.log", Range=range_header)


def test_read_file_aws_rejects_unsupported_extension(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    with pytest.raises(HTTPException) as exc:
        data_explorer.read_file("cache.parquet")
    assert exc.value.status_code == 415
    assert exc.value.detail == data_explorer.NOT_PREVIEWABLE_DETAIL


def test_read_file_aws_missing_404(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    mock_client = MagicMock()
    mock_client.head_object.side_effect = ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")

    with patch("boto3.client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc:
            data_explorer.read_file("missing.txt")
    assert exc.value.status_code == 404


def test_read_file_aws_rejects_traversal(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    with pytest.raises(HTTPException) as exc:
        data_explorer.read_file("../secret.txt")
    assert exc.value.status_code == 400


def test_read_file_preview(monkeypatch, tmp_path):
    (tmp_path / "notes.txt").write_text("hello world")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = data_explorer.read_file("notes.txt")

    assert result["content"] == "hello world"
    assert result["truncated"] is False
    assert result["path"] == "notes.txt"


def test_read_file_truncates_large_files(monkeypatch, tmp_path):
    big_content = "x" * (data_explorer.MAX_PREVIEW_BYTES + 100)
    (tmp_path / "big.log").write_text(big_content)
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = data_explorer.read_file("big.log")

    assert result["truncated"] is True
    assert len(result["content"]) == data_explorer.MAX_PREVIEW_BYTES


def test_read_file_rejects_unsupported_extension(monkeypatch, tmp_path):
    (tmp_path / "cache.parquet").write_bytes(b"\x00\x01\x02")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.read_file("cache.parquet")
    assert exc.value.status_code == 415
    assert exc.value.detail == data_explorer.NOT_PREVIEWABLE_DETAIL


def test_read_file_rejects_binary_file_with_no_extension_friendly_message(monkeypatch, tmp_path):
    # Regression for umbrella issue #6109 / follow-up #6112: a file like
    # `.git/index` has no recognised
    # extension at all, but the 415 detail should still read as a friendly
    # in-app message rather than a bare technical string.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_bytes(b"\x00\x01\x02\x03")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.read_file(".git/index")
    assert exc.value.status_code == 415
    assert exc.value.detail == data_explorer.NOT_PREVIEWABLE_DETAIL


def test_read_file_missing_404(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.read_file("missing.txt")
    assert exc.value.status_code == 404


def test_read_file_rejects_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        data_explorer.read_file("../secret.txt")
    assert exc.value.status_code == 400
