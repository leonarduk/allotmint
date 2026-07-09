import pandas as pd

from tests.test_timeseries_cache_base import import_cache, patch_s3_client


def test_list_cached_meta_tickers_local(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()

    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    (meta_dir / "ABC_L.parquet").write_bytes(b"x")
    (meta_dir / "BRK-B_US.parquet").write_bytes(b"x")
    (meta_dir / "not_a_cache_file.txt").write_text("ignore me", encoding="utf-8")

    assert cache.list_cached_meta_tickers() == [("ABC", "L"), ("BRK-B", "US")]


def test_list_cached_meta_tickers_empty_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    assert cache.list_cached_meta_tickers() == []


def test_list_cached_meta_tickers_s3(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    class FakePaginator:
        def paginate(self, Bucket, Prefix):  # noqa: N803 - boto3 API parameter names
            assert Bucket == "bucket"
            assert Prefix == "timeseries/meta/"
            yield {
                "Contents": [
                    {"Key": "timeseries/meta/ABC_L.parquet"},
                    {"Key": "timeseries/meta/XYZ_N.parquet"},
                    {"Key": "timeseries/meta/"},  # directory marker, no suffix match
                ]
            }

    class FakeS3:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

    patch_s3_client(monkeypatch, cache, FakeS3())

    assert cache.list_cached_meta_tickers() == [("ABC", "L"), ("XYZ", "N")]


def test_load_cached_meta_timeseries_full_reads_raw_file_without_dedup(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()

    df = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05")],
            "Open": [1.0, 1.0],
            "High": [1.0, 1.0],
            "Low": [1.0, 1.0],
            "Close": [1.0, 1.1],
            "Volume": [100, 100],
            "Ticker": ["ABC", "ABC"],
            "Source": ["TEST", "TEST"],
        }
    )
    path = tmp_path / "meta" / "ABC_L.parquet"
    path.parent.mkdir(parents=True)
    df.to_parquet(path, index=False)

    loaded = cache.load_cached_meta_timeseries_full("ABC", "L")
    assert len(loaded) == 2  # duplicate row preserved, not deduped


def test_load_cached_meta_timeseries_full_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    loaded = cache.load_cached_meta_timeseries_full("MISSING", "L")
    assert loaded.empty
