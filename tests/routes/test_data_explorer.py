import asyncio

import pytest
from fastapi import HTTPException

from backend.config import config
from backend.routes import data_explorer


def _run(coro):
    return asyncio.run(coro)


def test_list_directory_root(monkeypatch, tmp_path):
    (tmp_path / "timeseries").mkdir()
    (tmp_path / "accounts.json").write_text("{}")

    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = _run(data_explorer.list_directory(""))

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

    result = _run(data_explorer.list_directory("timeseries/meta"))

    assert result["path"] == "timeseries/meta"
    assert result["entries"][0]["path"] == "timeseries/meta/ABC_L.parquet"


def test_list_directory_missing_path_404(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        _run(data_explorer.list_directory("does-not-exist"))
    assert exc.value.status_code == 404


def test_list_directory_rejects_file_path(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        _run(data_explorer.list_directory("a.txt"))
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
        _run(data_explorer.list_directory(traversal))
    assert exc.value.status_code == 400


def test_list_directory_aws_not_supported(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        _run(data_explorer.list_directory(""))
    assert exc.value.status_code == 501


def test_read_file_preview(monkeypatch, tmp_path):
    (tmp_path / "notes.txt").write_text("hello world")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = _run(data_explorer.read_file("notes.txt"))

    assert result["content"] == "hello world"
    assert result["truncated"] is False
    assert result["path"] == "notes.txt"


def test_read_file_truncates_large_files(monkeypatch, tmp_path):
    big_content = "x" * (data_explorer.MAX_PREVIEW_BYTES + 100)
    (tmp_path / "big.log").write_text(big_content)
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    result = _run(data_explorer.read_file("big.log"))

    assert result["truncated"] is True
    assert len(result["content"]) == data_explorer.MAX_PREVIEW_BYTES


def test_read_file_rejects_unsupported_extension(monkeypatch, tmp_path):
    (tmp_path / "cache.parquet").write_bytes(b"\x00\x01\x02")
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        _run(data_explorer.read_file("cache.parquet"))
    assert exc.value.status_code == 415


def test_read_file_missing_404(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        _run(data_explorer.read_file("missing.txt"))
    assert exc.value.status_code == 404


def test_read_file_rejects_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    with pytest.raises(HTTPException) as exc:
        _run(data_explorer.read_file("../secret.txt"))
    assert exc.value.status_code == 400
