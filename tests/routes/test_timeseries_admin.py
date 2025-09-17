import asyncio
import builtins
import io
import sys

import pandas as pd

from backend.routes import timeseries_admin
from backend.config import config



def test_summarize_fields(monkeypatch):
    monkeypatch.setattr(
        timeseries_admin,
        "get_instrument_meta",
        lambda *_args, **_kwargs: {"name": "Test"},
    )

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
            ]),
            "Source": ["A", "B", "A"],
        }
    )

    summary = timeseries_admin._summarize(df, "XYZ", "L")

    assert summary["earliest"] == "2024-01-01"
    assert summary["latest"] == "2024-01-03"
    assert summary["completeness"] == 100.0
    assert summary["main_source"] == "A"


def test_summarize_missing_source(monkeypatch):
    monkeypatch.setattr(
        timeseries_admin,
        "get_instrument_meta",
        lambda symbol: {"name": f"Name for {symbol}"},
    )

    no_source_df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-01-05",
                "2024-01-08",
            ]),
            "Price": [1.0, 2.0],
        }
    )

    summary_no_source = timeseries_admin._summarize(no_source_df, "AAA", "L")

    assert summary_no_source["latest_source"] is None
    assert summary_no_source["main_source"] is None

    nan_source_df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-02-01",
                "2024-02-02",
            ]),
            "Source": [None, None],
        }
    )

    summary_nan_source = timeseries_admin._summarize(nan_source_df, "BBB", "M")

    assert summary_nan_source["latest_source"] is None
    assert summary_nan_source["main_source"] is None



def test_timeseries_admin_local(monkeypatch, tmp_path):
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
            ]),
            "Source": ["A", "B", "A"],
        }
    )

    meta_dir = tmp_path / "timeseries" / "meta"
    meta_dir.mkdir(parents=True)
    df.to_parquet(meta_dir / "ABC_L.parquet")
    # file without underscore should be skipped
    df.to_parquet(meta_dir / "INVALID.parquet")
    # empty dataframe should be skipped
    pd.DataFrame({"Date": pd.Series([], dtype="datetime64[ns]")}).to_parquet(
        meta_dir / "EMPTY_L.parquet"
    )

    monkeypatch.setattr(timeseries_admin, "get_instrument_meta", lambda *_: {"name": "Test"})
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    async def run():
        result = await timeseries_admin.timeseries_admin()
        assert result == [
            {
                "ticker": "ABC",
                "exchange": "L",
                "name": "Test",
                "earliest": "2024-01-01",
                "latest": "2024-01-03",
                "completeness": 100.0,
                "latest_source": "A",
                "main_source": "A",
            }
        ]

    asyncio.run(run())



def test_timeseries_admin_no_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    async def run():
        assert await timeseries_admin.timeseries_admin() == []

    asyncio.run(run())


def test_timeseries_admin_aws_no_bucket(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    async def run():
        assert await timeseries_admin.timeseries_admin() == []

    asyncio.run(run())


def test_timeseries_admin_aws_s3_empty(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "bucket")

    class DummyS3:
        def list_objects_v2(self, **_):
            return {"Contents": [], "IsTruncated": False}

    class DummyBoto3:
        def client(self, name):
            assert name == "s3"
            return DummyS3()

    class DummyExc(Exception):
        pass

    monkeypatch.setitem(sys.modules, "boto3", DummyBoto3())
    monkeypatch.setitem(sys.modules, "botocore.exceptions", type("e", (), {"ClientError": DummyExc}))

    async def run():
        assert await timeseries_admin.timeseries_admin() == []

    asyncio.run(run())


def test_timeseries_admin_aws_pagination(monkeypatch):
    bucket = "bucket"
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", bucket)

    frames_by_key = {
        "timeseries/meta/AAA_L.parquet": pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "Source": ["alpha", "alpha"],
            }
        ),
        "timeseries/meta/CCC_L.parquet": pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-02-01"]),
                "Source": ["gamma"],
            }
        ),
        "timeseries/meta/DDD_M.parquet": pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-03-01", "2024-03-04"]),
                "Source": ["delta", "delta"],
            }
        ),
    }

    read_parquet_keys: list[str] = []
    ensure_schema_calls: list[pd.DataFrame] = []

    def fake_read_parquet(buffer: io.BytesIO) -> pd.DataFrame:
        assert isinstance(buffer, io.BytesIO)
        key = buffer.getvalue().decode()
        read_parquet_keys.append(key)
        return frames_by_key[key]

    def fake_ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
        ensure_schema_calls.append(df)
        return df

    monkeypatch.setattr(timeseries_admin.pd, "read_parquet", fake_read_parquet)
    monkeypatch.setattr(timeseries_admin, "_ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(
        timeseries_admin,
        "get_instrument_meta",
        lambda symbol: {"name": f"Name for {symbol}"},
    )

    class DummyBody:
        def __init__(self, key: str) -> None:
            self._key = key

        def read(self) -> bytes:
            return self._key.encode()

    class DummyS3:
        def __init__(self) -> None:
            self.list_calls: list[dict[str, str]] = []
            self.get_calls: list[str] = []

        def list_objects_v2(self, **kwargs):
            self.list_calls.append(kwargs)
            expected = {"Bucket": bucket, "Prefix": "timeseries/meta/"}
            if len(self.list_calls) == 1:
                assert kwargs == expected
                return {
                    "Contents": [
                        {"Key": "timeseries/meta/AAA_L.parquet"},
                        {"Key": "timeseries/meta/BBB.parquet"},
                        {"Key": "timeseries/meta/bad.txt"},
                        {"Key": "timeseries/meta/EMPTY_L.parquet"},
                    ],
                    "IsTruncated": True,
                    "NextContinuationToken": "TOKEN123",
                }
            if len(self.list_calls) == 2:
                assert kwargs == {**expected, "ContinuationToken": "TOKEN123"}
                return {
                    "Contents": [
                        {"Key": "timeseries/meta/CCC_L.parquet"},
                        {"Key": "timeseries/meta/DDD_M.parquet"},
                        {"Key": "timeseries/meta/INVALID.parquet"},
                    ],
                    "IsTruncated": False,
                }
            raise AssertionError("Unexpected pagination request")

        def get_object(self, *, Bucket: str, Key: str):
            assert Bucket == bucket
            if Key == "timeseries/meta/EMPTY_L.parquet":
                self.get_calls.append(Key)
                return {"Body": None}
            assert Key in frames_by_key, f"Unexpected key fetched: {Key}"
            self.get_calls.append(Key)
            return {"Body": DummyBody(Key)}

    s3_client = DummyS3()

    class DummyBoto3:
        def client(self, name: str):
            assert name == "s3"
            return s3_client

    class DummyExc(Exception):
        pass

    monkeypatch.setitem(sys.modules, "boto3", DummyBoto3())
    monkeypatch.setitem(
        sys.modules,
        "botocore.exceptions",
        type("e", (), {"ClientError": DummyExc}),
    )

    async def run():
        summaries = await timeseries_admin.timeseries_admin()
        tickers = [summary["ticker"] for summary in summaries]
        assert tickers == ["AAA", "CCC", "DDD"]
        assert "EMPTY" not in tickers
        assert read_parquet_keys == [
            "timeseries/meta/AAA_L.parquet",
            "timeseries/meta/CCC_L.parquet",
            "timeseries/meta/DDD_M.parquet",
        ]
        assert len(ensure_schema_calls) == len(read_parquet_keys)

    asyncio.run(run())

    assert len(s3_client.list_calls) == 2
    assert s3_client.list_calls[1]["ContinuationToken"] == "TOKEN123"
    assert s3_client.get_calls == [
        "timeseries/meta/AAA_L.parquet",
        "timeseries/meta/EMPTY_L.parquet",
        "timeseries/meta/CCC_L.parquet",
        "timeseries/meta/DDD_M.parquet",
    ]


def test_refetch_and_rebuild(monkeypatch, tmp_path):
    df = pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=5)})

    def fake_load(t, e, days):
        assert t == "ABC"
        assert e == "L"
        return df

    monkeypatch.setattr(timeseries_admin, "load_meta_timeseries", fake_load)

    async def run():
        resp = await timeseries_admin.refetch_timeseries("abc", "l")
        assert resp == {"status": "ok", "rows": 5}

        cache_path = tmp_path / "cache.parquet"
        cache_path.write_text("x")

        def fake_cache_path(t, e):
            assert t == "ABC"
            assert e == "L"
            return cache_path

        monkeypatch.setattr(timeseries_admin, "meta_timeseries_cache_path", fake_cache_path)

        resp2 = await timeseries_admin.rebuild_cache("abc", "l")
        assert resp2 == {"status": "ok", "rows": 5}
        assert not cache_path.exists()

    asyncio.run(run())
