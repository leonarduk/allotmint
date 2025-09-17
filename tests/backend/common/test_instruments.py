import io
import json
import sys
from types import SimpleNamespace

import pytest

from backend.common import instruments


@pytest.mark.parametrize(
    "value,expected",
    [
        ("abc", "ABC"),
        ("a-bc123", "A-BC123"),
        ("XYZ", "XYZ"),
    ],
)
def test_validate_part_accepts_valid_symbols(value: str, expected: str) -> None:
    assert instruments._validate_part(value) == expected


@pytest.mark.parametrize("value", ["", "abc!", "with space", "inv.alid"])
def test_validate_part_rejects_invalid_symbols(value: str) -> None:
    with pytest.raises(ValueError):
        instruments._validate_part(value)


def test_instrument_path_generates_expected_locations(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)

    assert instruments._instrument_path("abc") == tmp_path / "Unknown" / "ABC.json"
    assert instruments._instrument_path("abc.l") == tmp_path / "L" / "ABC.json"
    assert instruments._instrument_path("cash") == tmp_path / "Cash" / "GBP.json"
    assert instruments._instrument_path("cash.usd") == tmp_path / "Cash" / "USD.json"


@pytest.mark.parametrize("ticker", ["bad$ticker", "abc.ba@d"])
def test_instrument_path_rejects_invalid_symbols(monkeypatch, tmp_path, ticker: str) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)

    with pytest.raises(ValueError):
        instruments._instrument_path(ticker)


def test_get_instrument_meta_reads_local_file_when_no_s3(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    monkeypatch.delenv(instruments.METADATA_PREFIX_ENV, raising=False)

    data = {"ticker": "ABC.L", "name": "Alpha"}
    path = tmp_path / "L" / "ABC.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))

    instruments.get_instrument_meta.cache_clear()
    assert instruments.get_instrument_meta("ABC.L") == data


def test_get_instrument_meta_prefers_s3_when_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.setenv(instruments.METADATA_BUCKET_ENV, "bucket")
    monkeypatch.setenv(instruments.METADATA_PREFIX_ENV, "prefix")

    payload = {"ticker": "ABC.L", "source": "s3"}

    def fake_client(name):
        assert name == "s3"

        def get_object(*, Bucket, Key):
            assert Bucket == "bucket"
            assert Key == "prefix/L/ABC.json"
            return {"Body": io.BytesIO(json.dumps(payload).encode("utf-8"))}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    instruments.get_instrument_meta.cache_clear()
    assert instruments.get_instrument_meta("ABC.L") == payload


def test_get_instrument_meta_falls_back_to_local_on_s3_error(monkeypatch, tmp_path, caplog) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.setenv(instruments.METADATA_BUCKET_ENV, "bucket")
    monkeypatch.setenv(instruments.METADATA_PREFIX_ENV, "prefix")

    payload = {"ticker": "ABC.L", "source": "local"}
    path = tmp_path / "L" / "ABC.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))

    def fake_client(name):
        assert name == "s3"

        def get_object(*, Bucket, Key):
            raise RuntimeError("boom")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    instruments.get_instrument_meta.cache_clear()
    with caplog.at_level("WARNING"):
        assert instruments.get_instrument_meta("ABC.L") == payload
    assert "falling back to local file" in caplog.text


def test_save_instrument_meta_writes_uploads_and_clears_cache(monkeypatch, tmp_path, caplog) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.setenv(instruments.METADATA_BUCKET_ENV, "bucket")
    monkeypatch.setenv(instruments.METADATA_PREFIX_ENV, "prefix")

    path = tmp_path / "L" / "ABC.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ticker": "ABC.L", "value": 1}))

    uploads = {}

    def fake_client(name):
        assert name == "s3"

        def get_object(*, Bucket, Key):
            raise RuntimeError("nope")

        def put_object(*, Bucket, Key, Body):
            uploads["Bucket"] = Bucket
            uploads["Key"] = Key
            uploads["Body"] = Body

        return SimpleNamespace(get_object=get_object, put_object=put_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    instruments.get_instrument_meta.cache_clear()
    with caplog.at_level("WARNING"):
        instruments.get_instrument_meta("ABC.L")

    new_data = {"ticker": "ABC.L", "value": 2}
    saved_path = instruments.save_instrument_meta("ABC", "L", new_data)
    assert saved_path == path

    assert json.loads(path.read_text()) == new_data
    assert uploads["Bucket"] == "bucket"
    assert uploads["Key"] == "prefix/L/ABC.json"
    assert json.loads(uploads["Body"].decode("utf-8")) == new_data

    assert instruments.get_instrument_meta("ABC.L") == new_data


def test_delete_instrument_meta_removes_file_and_handles_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    monkeypatch.delenv(instruments.METADATA_PREFIX_ENV, raising=False)

    path = tmp_path / "L" / "ABC.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ticker": "ABC.L"}))

    instruments.get_instrument_meta.cache_clear()
    assert instruments.get_instrument_meta("ABC.L") == {"ticker": "ABC.L"}

    instruments.delete_instrument_meta("ABC", "L")
    assert not path.exists()
    assert instruments.get_instrument_meta("ABC.L") == {}

    instruments.delete_instrument_meta("ABC", "L")


def test_list_instruments_adds_default_fields(monkeypatch, tmp_path) -> None:
    instruments.get_instrument_meta.cache_clear()
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)

    data = {"ticker": "ABC.L", "name": "Alpha"}
    path = tmp_path / "L" / "ABC.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))

    results = instruments.list_instruments()
    assert results == [
        {
            "ticker": "ABC.L",
            "name": "Alpha",
            "asset_class": None,
            "industry": None,
            "region": None,
            "grouping": None,
        }
    ]


def test_list_group_definitions_returns_empty_when_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(instruments.config, "data_root", tmp_path)
    instruments.list_group_definitions.cache_clear()
    try:
        assert instruments.list_group_definitions() == {}
    finally:
        instruments.list_group_definitions.cache_clear()


def test_list_group_definitions_loads_json(monkeypatch, tmp_path) -> None:
    root = tmp_path / "instruments" / "groupings"
    root.mkdir(parents=True, exist_ok=True)
    (root / "shared.json").write_text(json.dumps({"name": "Shared Group"}))
    (root / "balanced.json").write_text(json.dumps({"id": "balanced", "name": " Balanced "}))
    (root / "invalid.json").write_text("not-json")

    monkeypatch.setattr(instruments.config, "data_root", tmp_path)
    instruments.list_group_definitions.cache_clear()
    try:
        defs = instruments.list_group_definitions()
        assert defs == {
            "balanced": {"id": "balanced", "name": "Balanced"},
            "shared": {"id": "shared", "name": "Shared Group"},
        }
        assert "invalid" not in defs
    finally:
        instruments.list_group_definitions.cache_clear()
