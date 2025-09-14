import io
import json
import sys
import types
import zipfile
from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.query as query


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(query.router)
    return TestClient(app)


def test_resolve_tickers(monkeypatch):
    portfolios = [
        {
            "owner": "alice",
            "accounts": [{"holdings": [{"ticker": "abc.l"}, {"ticker": "def.l"}]}],
        },
        {
            "owner": "bob",
            "accounts": [{"holdings": [{"ticker": "xyz.l"}]}],
        },
    ]
    monkeypatch.setattr(query, "list_portfolios", lambda: portfolios)
    q = query.CustomQuery(
        start=date(2020, 1, 1),
        end=date(2020, 1, 2),
        owners=["Alice"],
        tickers=["def.l"],
    )
    assert query._resolve_tickers(q) == ["ABC.L", "DEF.L"]


def test_save_query_local(monkeypatch, tmp_path):
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    q = query.CustomQuery(
        start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"]
    )
    query._save_query_local("sample", q)
    saved = json.loads((tmp_path / "sample.json").read_text())
    assert saved["tickers"] == ["ABC.L"]


@pytest.fixture
def mock_s3(monkeypatch):
    storage: dict[tuple[str, str], bytes] = {}

    class FakeS3Client:
        def __init__(self, storage):
            self.storage = storage

        def put_object(self, Bucket, Key, Body):
            self.storage[(Bucket, Key)] = Body

        def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
            contents = [
                {"Key": key}
                for (bucket, key), _ in self.storage.items()
                if bucket == Bucket and key.startswith(Prefix)
            ]
            return {"Contents": contents}

        def get_object(self, Bucket, Key):
            body = io.BytesIO(self.storage[(Bucket, Key)])
            return {"Body": body}

    fake_boto3 = types.SimpleNamespace(client=lambda *_: FakeS3Client(storage))
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    return storage


def test_s3_helpers(monkeypatch, mock_s3):
    monkeypatch.setenv(query.DATA_BUCKET_ENV, "bucket")
    q = query.CustomQuery(
        start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"]
    )
    query._save_query_s3("s3-query", q)
    assert ("bucket", f"{query.QUERIES_PREFIX}s3-query.json") in mock_s3
    assert query._list_queries_s3() == ["s3-query"]
    loaded = query._load_query_s3("s3-query")
    assert loaded["tickers"] == ["ABC.L"]


def _setup_run_query(monkeypatch):
    monkeypatch.setattr(query, "_resolve_tickers", lambda q: ["ABC.L"])
    monkeypatch.setattr(
        query,
        "load_meta_timeseries_range",
        lambda *a, **k: pd.DataFrame({"close": [1, 2]}),
    )
    monkeypatch.setattr(query, "compute_var", lambda df: 1)
    monkeypatch.setattr(query, "get_security_meta", lambda t: {"name": "ABC"})


def test_run_query_json(monkeypatch):
    _setup_run_query(monkeypatch)
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "metrics": [query.Metric.VAR, query.Metric.META],
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["var"] == 1
    assert data["results"][0]["name"] == "ABC"


def test_run_query_csv(monkeypatch):
    _setup_run_query(monkeypatch)
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "metrics": [query.Metric.VAR, query.Metric.META],
        "format": "csv",
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().splitlines()
    assert lines[0] == "ticker,var,name"
    assert "ABC.L" in lines[1]


def test_run_query_xlsx(monkeypatch):
    _setup_run_query(monkeypatch)
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "metrics": [query.Metric.VAR, query.Metric.META],
        "format": "xlsx",
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.content.startswith(b"PK")
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    sheet = zf.read("xl/worksheets/sheet1.xml")
    assert b"ABC.L" in sheet


def test_saved_and_load_local(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    data = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "metrics": [],
    }
    (tmp_path / "sample.json").write_text(json.dumps(data))
    client = make_client()
    resp = client.get("/custom-query/saved")
    assert resp.status_code == 200
    assert resp.json() == ["sample"]
    resp = client.get("/custom-query/sample")
    assert resp.status_code == 200
    assert resp.json() == data


def test_saved_and_load_aws(monkeypatch, mock_s3):
    monkeypatch.setattr(query.config, "app_env", "aws")
    monkeypatch.setenv(query.DATA_BUCKET_ENV, "bucket")
    q = query.CustomQuery(
        start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"]
    )
    query._save_query_s3("remote", q)
    client = make_client()
    resp = client.get("/custom-query/saved")
    assert resp.status_code == 200
    assert resp.json() == ["remote"]
    resp = client.get("/custom-query/remote")
    assert resp.status_code == 200
    assert resp.json()["tickers"] == ["ABC.L"]
