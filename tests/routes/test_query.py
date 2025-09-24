import io
import json
import sys
import types
import zipfile
from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
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


def test_resolve_tickers_without_filters(monkeypatch):
    portfolios = [
        {
            "owner": "alice",
            "accounts": [{"holdings": [{"ticker": "abc.l"}]}],
        },
        {
            "owner": "bob",
            "accounts": [{"holdings": [{"ticker": "xyz.l"}]}],
        },
    ]
    monkeypatch.setattr(query, "list_portfolios", lambda: portfolios)
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 1, 2))
    assert query._resolve_tickers(q) == ["ABC.L", "XYZ.L"]


def test_slugify_handles_special_characters():
    assert query._slugify(" Demo Query! ") == "demo-query"


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


def test_save_query_s3_missing_bucket(monkeypatch):
    monkeypatch.delenv(query.DATA_BUCKET_ENV, raising=False)
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"])
    with pytest.raises(HTTPException) as exc:
        query._save_query_s3("missing", q)
    assert exc.value.status_code == 500


def test_list_queries_s3_without_bucket(monkeypatch):
    monkeypatch.delenv(query.DATA_BUCKET_ENV, raising=False)
    assert query._list_queries_s3() == []


def test_list_queries_s3_handles_pagination(monkeypatch):
    class FakePager:
        def __init__(self):
            self.calls = 0

        def list_objects_v2(self, **params):
            self.calls += 1
            if self.calls == 1:
                assert "ContinuationToken" not in params
                return {
                    "Contents": [
                        {"Key": f"{query.QUERIES_PREFIX}first.json"},
                    ],
                    "IsTruncated": True,
                    "NextContinuationToken": "token-1",
                }
            assert params.get("ContinuationToken") == "token-1"
            return {
                "Contents": [
                    {"Key": f"{query.QUERIES_PREFIX}second.json"},
                ],
                "IsTruncated": False,
            }

    pager = FakePager()
    fake_boto3 = types.SimpleNamespace(client=lambda *_: pager)
    monkeypatch.setenv(query.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    assert query._list_queries_s3() == ["first", "second"]
    assert pager.calls == 2


def test_load_query_s3_missing_bucket(monkeypatch):
    monkeypatch.delenv(query.DATA_BUCKET_ENV, raising=False)
    with pytest.raises(HTTPException) as exc:
        query._load_query_s3("missing")
    assert exc.value.status_code == 404


def test_load_query_s3_missing_body(monkeypatch):
    class FakeBody:
        def read(self):
            return b""

    class FakeClient:
        def get_object(self, **kwargs):
            return {"Body": FakeBody()}

    fake_boto3 = types.SimpleNamespace(client=lambda *_: FakeClient())
    monkeypatch.setenv(query.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    with pytest.raises(HTTPException) as exc:
        query._load_query_s3("empty")
    assert exc.value.status_code == 404


def _setup_run_query(monkeypatch):
    monkeypatch.setattr(query, "_resolve_tickers", lambda q: ["ABC.L"])
    monkeypatch.setattr(
        query,
        "load_meta_timeseries_range",
        lambda *a, **k: pd.DataFrame({"close": [1, 2]}),
    )
    monkeypatch.setattr(query, "compute_var", lambda df: 1)
    monkeypatch.setattr(query, "get_security_meta", lambda t: {"name": "ABC"})


def test_run_query_skips_timeseries_when_no_metrics(monkeypatch):
    calls = {"count": 0}

    def fake_loader(*args, **kwargs):
        calls["count"] += 1
        return pd.DataFrame({"Close": [1, 2]})

    monkeypatch.setattr(query, "_resolve_tickers", lambda q: ["ABC.L"])
    monkeypatch.setattr(query, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(query, "get_security_meta", lambda t: {})

    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "metrics": [],
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    assert resp.json() == {"results": [{"ticker": "ABC.L"}]}
    assert calls["count"] == 0


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


def test_run_query_without_targets(monkeypatch):
    monkeypatch.setattr(query, "_resolve_tickers", lambda q: [])
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


def test_run_query_saves_named_query_local(monkeypatch, tmp_path):
    monkeypatch.setattr(query, "_resolve_tickers", lambda q: ["ABC.L"])
    monkeypatch.setattr(
        query,
        "load_meta_timeseries_range",
        lambda *a, **k: pd.DataFrame({"Close": [1, 2]}),
    )
    monkeypatch.setattr(query, "compute_var", lambda df: None)
    monkeypatch.setattr(query, "get_security_meta", lambda t: {})
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    monkeypatch.setattr(query.config, "app_env", "local")
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "name": " Demo Name ",
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    assert (tmp_path / "demo-name.json").exists()


def test_run_query_saves_named_query_aws(monkeypatch):
    saved: dict[str, str] = {}

    def fake_save(slug: str, q: query.CustomQuery) -> None:
        saved["slug"] = slug
        saved["tickers"] = ",".join(q.tickers or [])

    monkeypatch.setattr(query, "_resolve_tickers", lambda q: ["ABC.L"])
    monkeypatch.setattr(
        query,
        "load_meta_timeseries_range",
        lambda *a, **k: pd.DataFrame({"Close": [1, 2]}),
    )
    monkeypatch.setattr(query, "compute_var", lambda df: None)
    monkeypatch.setattr(query, "get_security_meta", lambda t: {})
    monkeypatch.setattr(query, "_save_query_s3", fake_save)
    monkeypatch.setattr(query.config, "app_env", "aws")
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
        "name": "S3 Query",
    }
    resp = client.post("/custom-query/run", json=body)
    assert resp.status_code == 200
    assert saved == {"slug": "s3-query", "tickers": "ABC.L"}


def test_list_saved_queries_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    missing = tmp_path / "missing"
    monkeypatch.setattr(query, "QUERIES_DIR", missing)
    client = make_client()
    resp = client.get("/custom-query/saved")
    assert resp.status_code == 200
    assert resp.json() == []


def test_load_query_missing_local_file(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    client = make_client()
    resp = client.get("/custom-query/missing")
    assert resp.status_code == 404


def test_save_query_route_aws(monkeypatch):
    captured: dict[str, str] = {}

    def fake_save(slug: str, q: query.CustomQuery) -> None:
        captured["slug"] = slug
        captured["ticker"] = (q.tickers or [""])[0]

    monkeypatch.setattr(query.config, "app_env", "aws")
    monkeypatch.setattr(query, "_save_query_s3", fake_save)
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
    }
    resp = client.post("/custom-query/demo-save", json=body)
    assert resp.status_code == 200
    assert resp.json() == {"saved": "demo-save"}
    assert captured == {"slug": "demo-save", "ticker": "ABC.L"}


def test_save_query_route_local(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    client = make_client()
    body = {
        "start": "2020-01-01",
        "end": "2020-01-02",
        "tickers": ["ABC.L"],
    }
    resp = client.post("/custom-query/local", json=body)
    assert resp.status_code == 200
    assert resp.json() == {"saved": "local"}
    assert (tmp_path / "local.json").exists()
