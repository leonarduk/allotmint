import pandas as pd
import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common.errors import ValidationFailure
from backend.routes import timeseries_edit
from backend.timeseries import cache


@pytest.mark.parametrize(
    "ticker,exchange,expected",
    [
        ("abc", "l", ("ABC", "L")),
        ("abc.l", None, ("ABC", "L")),
    ],
)
def test_resolve_ticker_exchange_direct(ticker, exchange, expected):
    assert timeseries_edit._resolve_ticker_exchange(ticker, exchange) == expected


def test_resolve_ticker_exchange_inferred(monkeypatch):
    def fake_resolve(t, latest):
        assert t == "ABC"
        return ("ABC", "L")

    monkeypatch.setattr(timeseries_edit.instrument_api, "_resolve_full_ticker", fake_resolve)
    monkeypatch.setattr(timeseries_edit.instrument_api, "_LATEST_PRICES", {})

    assert timeseries_edit._resolve_ticker_exchange("abc", None) == ("ABC", "L")


def test_resolve_ticker_exchange_error(monkeypatch):
    monkeypatch.setattr(timeseries_edit.instrument_api, "_resolve_full_ticker", lambda *_: None)
    monkeypatch.setattr(timeseries_edit.instrument_api, "_LATEST_PRICES", {})

    with pytest.raises(ValidationFailure) as exc:
        timeseries_edit._resolve_ticker_exchange("abc", None)
    assert exc.value.status_code == 400
    assert "could not be inferred" in exc.value.detail


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    app = FastAPI()
    app.include_router(timeseries_edit.router)
    return TestClient(app)


def test_post_json_and_get_format(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    data = [
        {
            "Date": "2024-01-01",
            "Open": 1.0,
            "High": 2.0,
            "Low": 0.5,
            "Close": 1.5,
            "Volume": 100,
            "Ticker": "",
            "Source": "",
        },
        {
            "Date": "2024-01-02",
            "Open": 1.1,
            "High": 2.1,
            "Low": 0.6,
            "Close": 1.6,
            "Volume": 110,
            "Ticker": "",
            "Source": "",
        },
    ]
    resp = client.post("/timeseries/edit?ticker=ABC&exchange=L", json=data)
    assert resp.status_code == 200
    assert resp.json()["rows"] == 2

    path = timeseries_edit.meta_timeseries_cache_path("ABC", "L")
    df = pd.read_parquet(path)
    assert len(df) == 2
    assert list(df["Ticker"]) == ["ABC", "ABC"]
    assert list(df["Source"]) == ["Manual", "Manual"]

    resp = client.get("/timeseries/edit?ticker=ABC&exchange=L")
    assert resp.status_code == 200
    returned = resp.json()
    assert returned[0]["Date"] == "2024-01-01"


def test_post_csv_saves_parquet(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    csv_data = "Date,Open,High,Low,Close,Volume\n2024-01-01,1,2,0.5,1.5,100\n2024-01-02,1.1,2.1,0.6,1.6,110\n"
    headers = {"Content-Type": "text/csv"}
    resp = client.post(
        "/timeseries/edit?ticker=XYZ&exchange=L",
        content=csv_data,
        headers=headers,
    )
    assert resp.status_code == 200
    path = timeseries_edit.meta_timeseries_cache_path("XYZ", "L")
    df = pd.read_parquet(path)
    assert df.loc[0, "Close"] == 1.5
    assert list(df["Ticker"]) == ["XYZ", "XYZ"]
    assert list(df["Source"]) == ["Manual", "Manual"]


def test_get_missing_file(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/timeseries/edit?ticker=NOPE&exchange=L")
    assert resp.status_code == 200
    assert resp.json() == []


def test_move_timeseries_removes_source_without_duplication(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    data = [{"Date": "2024-01-01", "Close": 1.5}]
    assert client.post("/timeseries/edit?ticker=IONQ&exchange=L", json=data).status_code == 200

    resp = client.post("/timeseries/edit/move?ticker=IONQ&source_exchange=L&destination_exchange=N")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "rows": 1, "ticker": "IONQ", "exchange": "N"}
    assert client.get("/timeseries/edit?ticker=IONQ&exchange=L").json() == []
    assert len(client.get("/timeseries/edit?ticker=IONQ&exchange=N").json()) == 1


def test_move_timeseries_refuses_to_overwrite_destination(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    data = [{"Date": "2024-01-01", "Close": 1.5}]
    client.post("/timeseries/edit?ticker=IONQ&exchange=L", json=data)
    client.post("/timeseries/edit?ticker=IONQ&exchange=N", json=data)

    resp = client.post("/timeseries/edit/move?ticker=IONQ&source_exchange=L&destination_exchange=N")

    assert resp.status_code == 409
    assert client.get("/timeseries/edit?ticker=IONQ&exchange=L").json()


def test_move_timeseries_missing_source_returns_404(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.post("/timeseries/edit/move?ticker=IONQ&source_exchange=L&destination_exchange=N")

    assert resp.status_code == 404


class _FakeS3Client:
    def __init__(self, *, fail_delete=False):
        self.fail_delete = fail_delete
        self.deleted = []
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)

    def delete_object(self, Bucket, Key):  # noqa: N803 - matches boto3 signature
        if self.fail_delete and Key.endswith("-L.parquet"):
            raise RuntimeError("simulated S3 delete failure")
        self.deleted.append((Bucket, Key))


class _FakeDataFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not rows
        self.to_parquet_calls = []

    def to_parquet(self, destination, index=False):
        self.to_parquet_calls.append(destination)

    def __len__(self):
        return len(self._rows)


def _setup_s3_move(monkeypatch, *, fake_client, source_exists=True, destination_exists=False):
    fake_df = _FakeDataFrame([{"Close": 1.5}])
    monkeypatch.setattr(
        timeseries_edit,
        "meta_timeseries_cache_path",
        lambda ticker, exchange: f"s3://bucket/{ticker}-{exchange}.parquet",
    )
    monkeypatch.setattr(
        timeseries_edit,
        "has_cached_meta_timeseries",
        lambda ticker, exchange: destination_exists if exchange == "N" else source_exists,
    )
    monkeypatch.setattr(timeseries_edit, "_load_timeseries", lambda ticker, exchange: fake_df)
    monkeypatch.setattr(timeseries_edit, "_s3_client", lambda: fake_client)
    return fake_df


def test_move_timeseries_s3_success_writes_then_deletes(monkeypatch):
    fake_client = _FakeS3Client()
    _setup_s3_move(monkeypatch, fake_client=fake_client)

    rows = timeseries_edit._move_timeseries("IONQ", "L", "N")

    assert rows == 1
    assert len(fake_client.puts) == 1
    assert fake_client.puts[0]["IfNoneMatch"] == "*"
    assert fake_client.deleted == [("bucket", "IONQ-L.parquet")]


def test_move_timeseries_s3_delete_failure_reports_error(monkeypatch):
    from backend.common.errors import InternalServiceError

    fake_client = _FakeS3Client(fail_delete=True)
    _setup_s3_move(monkeypatch, fake_client=fake_client)

    with pytest.raises(InternalServiceError) as exc:
        timeseries_edit._move_timeseries("IONQ", "L", "N")

    assert len(fake_client.puts) == 1
    assert fake_client.deleted == [("bucket", "IONQ-N.parquet")]
    assert "rolled back" in str(exc.value)


def test_move_timeseries_s3_conditional_conflict_returns_409(monkeypatch):
    class ConflictS3(_FakeS3Client):
        def put_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")

    fake_client = ConflictS3()
    _setup_s3_move(monkeypatch, fake_client=fake_client)

    with pytest.raises(timeseries_edit.HTTPException) as exc:
        timeseries_edit._move_timeseries("IONQ", "L", "N")

    assert exc.value.status_code == 409
    assert fake_client.deleted == []


def test_load_timeseries_missing_s3_object_returns_empty(monkeypatch):
    class MissingS3:
        def head_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")

    monkeypatch.setattr(timeseries_edit, "meta_timeseries_cache_path", lambda *_: "s3://bucket/missing.parquet")
    monkeypatch.setattr(timeseries_edit, "_s3_client", lambda: MissingS3())

    assert timeseries_edit._load_timeseries("NOPE", "L").empty


def test_load_timeseries_s3_metadata_failure_is_not_a_cache_miss(monkeypatch):
    class DeniedS3:
        def head_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")

    monkeypatch.setattr(timeseries_edit, "meta_timeseries_cache_path", lambda *_: "s3://bucket/denied.parquet")
    monkeypatch.setattr(timeseries_edit, "_s3_client", lambda: DeniedS3())

    with pytest.raises(timeseries_edit.InternalServiceError):
        timeseries_edit._load_timeseries("NOPE", "L")


def test_move_timeseries_case_insensitive_exchange_rejected(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    data = [{"Date": "2024-01-01", "Close": 1.5}]
    client.post("/timeseries/edit?ticker=IONQ&exchange=L", json=data)

    resp = client.post("/timeseries/edit/move?ticker=IONQ&source_exchange=l&destination_exchange=L")

    assert resp.status_code == 400
