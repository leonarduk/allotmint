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
    # Selected tickers restrict the query; they are not unioned with every
    # holding of the selected owners (#7380).
    assert query._resolve_tickers(q) == ["DEF.L"]


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
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"])
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
                {"Key": key} for (bucket, key), _ in self.storage.items() if bucket == Bucket and key.startswith(Prefix)
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
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"])
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
    monkeypatch.setattr(query, "compute_var_with_basis", lambda df, **k: (1, "total"))
    monkeypatch.setattr(query, "get_security_meta", lambda t: {"name": "ABC"})


def test_run_query_skips_timeseries_when_no_metrics(monkeypatch):
    calls = {"loader": 0, "compute": 0}

    def fake_loader(*args, **kwargs):
        calls["loader"] += 1
        return pd.DataFrame({"Close": [1, 2]})

    def fake_compute(df, **kwargs):
        calls["compute"] += 1
        return 123, "total"

    monkeypatch.setattr(query, "_resolve_tickers", lambda q: ["ABC.L"])
    monkeypatch.setattr(query, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(query, "compute_var_with_basis", fake_compute)
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
    assert calls == {"loader": 0, "compute": 0}


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
    assert data["results"][0]["return_basis"] == "total"
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
    assert lines[0] == "ticker,var,return_basis,name"
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
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
    saved_entries = resp.json()
    assert any(
        entry.get("id") == "sample" and entry.get("name") == "sample" and entry.get("params") == data
        for entry in saved_entries
    )
    resp = client.get("/custom-query/saved", params={"detailed": "0"})
    assert resp.status_code == 200
    assert resp.json() == ["sample"]
    resp = client.get("/custom-query/sample")
    assert resp.status_code == 200
    assert resp.json() == data


def test_saved_and_load_aws(monkeypatch, mock_s3):
    monkeypatch.setattr(query.config, "app_env", "aws")
    monkeypatch.setenv(query.DATA_BUCKET_ENV, "bucket")
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"])
    query._save_query_s3("remote", q)
    client = make_client()
    resp = client.get("/custom-query/saved")
    assert resp.status_code == 200
    saved_entries = resp.json()
    expected_params = q.model_dump(mode="json")
    expected_params.pop("name", None)
    assert any(
        entry.get("id") == "remote" and entry.get("name") == "remote" and entry.get("params") == expected_params
        for entry in saved_entries
    )
    resp = client.get("/custom-query/saved", params={"detailed": "0"})
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
    monkeypatch.setattr(query, "compute_var_with_basis", lambda df, **k: (None, "price"))
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
    monkeypatch.setattr(query, "compute_var_with_basis", lambda df, **k: (None, "price"))
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


# ---------------------------------------------------------------------------
# Path traversal rejection tests
# ---------------------------------------------------------------------------


def test_load_query_local_dotdot_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        query._load_query_local("../etc/passwd")
    assert exc_info.value.status_code == 404


def test_save_query_local_dotdot_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 1, 2), tickers=["ABC.L"])
    with pytest.raises(HTTPException) as exc_info:
        query._save_query_local("../evil", q)
    assert exc_info.value.status_code == 400


def test_load_query_route_traversal_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    monkeypatch.setattr(query, "REPO_QUERIES_DIR", tmp_path)
    client = make_client()
    # The HTTP layer encodes '/' so the slug received is the literal string "../etc/passwd"
    resp = client.get("/custom-query/..%2Fetc%2Fpasswd")
    assert resp.status_code == 404


def test_save_query_route_traversal_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    client = make_client()
    body = {"start": "2020-01-01", "end": "2020-01-02", "tickers": ["ABC.L"]}
    # The HTTP layer encodes '/' so the path is normalised before reaching the route.
    # A status of 400 (safe_join blocked) or 404 (URL-layer normalisation blocked) is
    # both acceptable; 422 (Pydantic validation failure) must never occur here.
    resp = client.post("/custom-query/..%2Fevil", json=body)
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# REPO_QUERIES_DIR fallback — traversal and regression tests
# ---------------------------------------------------------------------------


def test_load_query_local_traversal_blocked_regardless_of_dir_config(monkeypatch, tmp_path):
    """Traversal slug is rejected by safe_join even with a separate REPO_QUERIES_DIR.

    Note: both safe_join calls in _load_query_local use the same slug logic, so a
    traversal slug is always caught by the *first* call (QUERIES_DIR) — the second
    (REPO_QUERIES_DIR) call is defence-in-depth that cannot be reached with a
    traversal slug because both guards share the same slug argument.
    """
    queries_dir = tmp_path / "user_queries"
    queries_dir.mkdir()
    repo_queries_dir = tmp_path / "repo_queries"
    repo_queries_dir.mkdir()
    monkeypatch.setattr(query, "QUERIES_DIR", queries_dir)
    monkeypatch.setattr(query, "REPO_QUERIES_DIR", repo_queries_dir)

    with pytest.raises(HTTPException) as exc_info:
        query._load_query_local("../etc/passwd")
    assert exc_info.value.status_code == 404


def test_load_query_local_fallback_loads_from_repo_dir(monkeypatch, tmp_path):
    """A slug absent from QUERIES_DIR but present in REPO_QUERIES_DIR is returned."""
    queries_dir = tmp_path / "user_queries"
    queries_dir.mkdir()
    repo_queries_dir = tmp_path / "repo_queries"
    repo_queries_dir.mkdir()
    payload = {"start": "2020-01-01", "end": "2020-01-02", "tickers": ["XYZ.L"]}
    (repo_queries_dir / "repo-query.json").write_text(json.dumps(payload))
    monkeypatch.setattr(query, "QUERIES_DIR", queries_dir)
    monkeypatch.setattr(query, "REPO_QUERIES_DIR", repo_queries_dir)

    result = query._load_query_local("repo-query")

    assert result["tickers"] == ["XYZ.L"]


# --- holding metrics, save and GET export (#7380) ---------------------------

_HOLDING_PORTFOLIOS = [
    {
        "owner": "alice",
        "accounts": [
            {"holdings": [{"ticker": "ABC.L", "units": 10, "acquired_date": "2019-01-01", "cost_basis_gbp": 50}]},
            {
                "holdings": [
                    {"ticker": "ABC.L", "units": 5, "acquired_date": "2019-06-01", "cost_basis_gbp": 30},
                    {"ticker": "NEW.L", "units": 2, "acquired_date": "2020-06-01", "cost_basis_gbp": 7},
                    {"ticker": "CASH.GBP", "units": 100},
                ]
            },
        ],
    },
    {"owner": "bob", "accounts": [{"holdings": [{"ticker": "ABC.L", "units": 1}]}]},
]

# GBP closes by (symbol, date): ABC rises 2 -> 3, NEW is 4 at the end.
_PRICES = {
    ("ABC", date(2020, 1, 1)): 2.0,
    ("ABC", date(2020, 12, 31)): 3.0,
    ("NEW", date(2020, 12, 31)): 4.0,
}

# Alice's history replays to her current holdings; Bob has none on file.
_TRANSACTIONS = {
    "alice": [
        {"date": "2019-01-01", "type": "BUY", "ticker": "ABC.L", "units": 10},
        {"date": "2019-06-01", "type": "BUY", "ticker": "ABC.L", "units": 5},
        {"date": "2020-06-01", "type": "BUY", "ticker": "NEW.L", "units": 2},
    ],
}


def _fake_load_transactions(owner):
    if owner not in _TRANSACTIONS:
        raise FileNotFoundError(owner)
    return _TRANSACTIONS[owner]


@pytest.fixture
def holdings_env(monkeypatch):
    monkeypatch.setattr(query, "list_portfolios", lambda: _HOLDING_PORTFOLIOS)
    monkeypatch.setattr(query, "load_transactions", _fake_load_transactions)
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (_PRICES.get((sym, d)), None))
    monkeypatch.setattr(query, "get_security_meta", lambda t: {"name": t.lower()})


def _holding_query(**kwargs):
    base = {"start": date(2020, 1, 1), "end": date(2020, 12, 31), "metrics": [query.Metric.MARKET_VALUE_GBP]}
    return query.CustomQuery(**{**base, **kwargs})


def test_holding_rows_sum_accounts_per_owner_and_ticker(holdings_env):
    rows = query.run_query(_holding_query(owners=["alice"], tickers=["ABC.L"]))["results"]
    assert rows == [{"owner": "alice", "ticker": "ABC.L", "units": 15.0, "market_value_gbp": 45.0}]


def test_gain_measures_from_start_price_or_cost_when_bought_in_range(holdings_env):
    q = _holding_query(owners=["alice"], metrics=[query.Metric.GAIN_GBP])
    rows = {r["ticker"]: r for r in query.run_query(q)["results"]}
    # Held at the start: 15 units x (3 - 2).
    assert rows["ABC.L"]["start_value_gbp"] == 30.0
    assert rows["ABC.L"]["gain_gbp"] == 15.0
    # Bought mid-range: from its cost of 7 to 2 x 4.
    assert rows["NEW.L"]["start_value_gbp"] == 7.0
    assert rows["NEW.L"]["gain_gbp"] == 1.0
    # Cash isn't replayed by the history, so its units at the end of a past
    # range are unknown.
    assert rows["CASH.GBP"]["gain_gbp"] is None


def test_unpriced_holding_value_is_none_not_understated(holdings_env, monkeypatch):
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda *a: (None, None))
    rows = query.run_query(_holding_query(tickers=["ABC.L"]))["results"]
    assert [r["market_value_gbp"] for r in rows] == [None, None]


def test_holding_metrics_merge_per_ticker_metrics(holdings_env):
    q = _holding_query(owners=["alice"], tickers=["ABC.L"], metrics=[query.Metric.MARKET_VALUE_GBP, query.Metric.META])
    assert query.run_query(q)["results"] == [
        {"owner": "alice", "ticker": "ABC.L", "units": 15.0, "market_value_gbp": 45.0, "name": "abc.l"}
    ]


def test_get_run_exports_csv_attachment(holdings_env):
    resp = make_client().get(
        "/custom-query/run",
        params={
            "start": "2020-01-01",
            "end": "2020-12-31",
            "owners": "alice",
            "tickers": "ABC.L",
            "metrics": "market_value_gbp,gain_gbp",
            "format": "csv",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == "attachment; filename=custom-query.csv"
    lines = resp.text.strip().splitlines()
    assert lines[0] == "owner,ticker,units,market_value_gbp,start_value_gbp,gain_gbp"
    assert lines[1] == "alice,ABC.L,15.0,45.0,30.0,15.0"


def test_get_run_rejects_unknown_metric(holdings_env):
    resp = make_client().get(
        "/custom-query/run", params={"start": "2020-01-01", "end": "2020-12-31", "metrics": "bogus"}
    )
    assert resp.status_code == 422


def test_save_route_slugifies_name(monkeypatch, tmp_path):
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    body = {"name": "My ISA gains!", "start": "2020-01-01", "end": "2020-12-31", "metrics": ["gain_gbp"]}
    resp = make_client().post("/custom-query/save", json=body)
    assert resp.status_code == 200
    assert resp.json() == {"id": "my-isa-gains", "saved": "my-isa-gains"}
    assert json.loads((tmp_path / "my-isa-gains.json").read_text())["metrics"] == ["gain_gbp"]


def test_save_route_requires_a_name(monkeypatch, tmp_path):
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path)
    resp = make_client().post("/custom-query/save", json={"start": "2020-01-01", "end": "2020-12-31"})
    assert resp.status_code == 400
    assert not list(tmp_path.iterdir())


def test_price_steps_back_past_an_empty_close(holdings_env, monkeypatch):
    # Nothing stored for the end date or the day before (an empty bar), so
    # the value comes from the latest usable close within the week.
    prices = {("ABC", date(2020, 12, 29)): 3.0}
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (prices.get((sym, d)), None))
    rows = query.run_query(_holding_query(owners=["alice"], tickers=["ABC.L"]))["results"]
    assert rows[0]["market_value_gbp"] == 45.0


def test_top_up_inside_range_splits_start_price_and_cost(holdings_env, monkeypatch):
    # 10 units held before the range at 1.00, 10 more bought inside it; the
    # pooled cost of all 20 is 40 (2.00 each). Ends at 3.00.
    portfolios = [
        {
            "owner": "alice",
            "accounts": [
                {"holdings": [{"ticker": "TOP.L", "units": 20, "acquired_date": "2020-06-01", "cost_basis_gbp": 40}]}
            ],
        }
    ]
    tx = [
        {"date": "2019-01-01", "type": "BUY", "ticker": "TOP.L", "units": 10},
        {"date": "2020-06-01", "type": "BUY", "ticker": "TOP.L", "units": 10},
    ]
    prices = {("TOP", date(2020, 1, 1)): 1.0, ("TOP", date(2020, 12, 31)): 3.0}
    monkeypatch.setattr(query, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(query, "load_transactions", lambda owner: tx)
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (prices.get((sym, d)), None))
    row = query.run_query(_holding_query(metrics=[query.Metric.GAIN_GBP]))["results"][0]
    # Not the whole pooled cost (40): 10 x 1.00 held + 10 x 2.00 bought.
    assert row["start_value_gbp"] == 30.0
    assert row["gain_gbp"] == 30.0


def test_gain_falls_back_to_start_price_when_history_does_not_replay(holdings_env, monkeypatch):
    # The history only explains 10 of alice's 15 ABC units, so it isn't
    # trusted: for a range ending today, all 15 count at the start-date price.
    partial = [{"date": "2019-01-01", "type": "BUY", "ticker": "ABC.L", "units": 10}]
    monkeypatch.setattr(query, "load_transactions", lambda owner: partial)
    start = date(2020, 1, 1)
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (2.0 if d == start else 3.0, None))
    q = _holding_query(owners=["alice"], tickers=["ABC.L"], end=date.today(), metrics=[query.Metric.GAIN_GBP])
    row = query.run_query(q)["results"][0]
    assert row["start_value_gbp"] == 30.0
    assert row["gain_gbp"] == 15.0


def test_get_run_per_ticker_metrics_give_one_row_per_ticker(holdings_env):
    resp = make_client().get(
        "/custom-query/run",
        params={"start": "2020-01-01", "end": "2020-12-31", "owners": "alice,bob", "metrics": "meta"},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "results": [
            {"ticker": "ABC.L", "name": "abc.l"},
            {"ticker": "CASH.GBP", "name": "cash.gbp"},
            {"ticker": "NEW.L", "name": "new.l"},
        ]
    }


def test_per_ticker_metrics_keep_the_owner_filter_when_tickers_are_selected(holdings_env):
    # Bob doesn't hold NEW.L: selecting him and it must not produce a row.
    q = query.CustomQuery(
        start=date(2020, 1, 1), end=date(2020, 12, 31), owners=["bob"], tickers=["NEW.L"], metrics=[query.Metric.META]
    )
    assert query.run_query(q) == {"results": []}
    q = q.model_copy(update={"tickers": ["ABC.L", "NEW.L"]})
    assert query.run_query(q) == {"results": [{"ticker": "ABC.L", "name": "abc.l"}]}


def test_tickers_without_owners_are_queried_even_if_nobody_holds_them(holdings_env):
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 12, 31), tickers=["ZZZ.L"], metrics=["meta"])
    assert query.run_query(q) == {"results": [{"ticker": "ZZZ.L", "name": "zzz.l"}]}


def test_historical_range_values_the_units_held_at_its_end(holdings_env, monkeypatch):
    # Range 2018-12-01..2019-03-01: alice's first 10 ABC (bought 2019-01-01)
    # are held at the end; the 5 bought in June are not yet. Pooled cost is
    # 80 for 15 units, so the 10 bought inside the range start at 53.33.
    prices = {("ABC", date(2019, 3, 1)): 6.0}
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (prices.get((sym, d)), None))
    q = query.CustomQuery(
        start=date(2018, 12, 1),
        end=date(2019, 3, 1),
        owners=["alice"],
        tickers=["ABC.L"],
        metrics=[query.Metric.MARKET_VALUE_GBP, query.Metric.GAIN_GBP],
    )
    row = query.run_query(q)["results"][0]
    assert row["units"] == 10.0
    assert row["market_value_gbp"] == 60.0
    assert row["start_value_gbp"] == 53.33
    assert row["gain_gbp"] == 6.67


def test_in_range_buys_use_what_was_paid_not_a_later_average(holdings_env, monkeypatch):
    # 10 held before the range (start price 1.00), 10 bought inside it for
    # 20.00 in total, 10 more bought after it for 100.00. The pooled average
    # (130 / 30) must not leak into the range: start = 10 x 1.00 + 20.00.
    portfolios = [
        {
            "owner": "alice",
            "accounts": [
                {"holdings": [{"ticker": "TOP.L", "units": 30, "acquired_date": "2021-03-01", "cost_basis_gbp": 130}]}
            ],
        }
    ]
    tx = [
        {"date": "2019-01-01", "type": "BUY", "ticker": "TOP.L", "units": 10, "amount_minor": 1000},
        {"date": "2020-06-01", "type": "BUY", "ticker": "TOP.L", "units": 10, "amount_minor": 2000},
        {"date": "2021-03-01", "type": "BUY", "ticker": "TOP.L", "units": 10, "amount_minor": 10000},
    ]
    prices = {("TOP", date(2020, 1, 1)): 1.0, ("TOP", date(2020, 12, 31)): 3.0}
    monkeypatch.setattr(query, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(query, "load_transactions", lambda owner: tx)
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (prices.get((sym, d)), None))
    row = query.run_query(_holding_query(metrics=[query.Metric.MARKET_VALUE_GBP, query.Metric.GAIN_GBP]))["results"][0]
    assert row["units"] == 20.0
    assert row["market_value_gbp"] == 60.0
    assert row["start_value_gbp"] == 30.0
    assert row["gain_gbp"] == 30.0


def test_save_route_name_cannot_escape_the_queries_dir(monkeypatch, tmp_path):
    queries_dir = tmp_path / "queries"
    monkeypatch.setattr(query.config, "app_env", "local")
    monkeypatch.setattr(query, "QUERIES_DIR", queries_dir)
    body = {"name": "../../etc/passwd", "start": "2020-01-01", "end": "2020-12-31"}
    resp = make_client().post("/custom-query/save", json=body)
    # _slugify keeps only [a-z0-9-], so separators and dots never reach the path.
    assert resp.json()["id"] == "etc-passwd"
    assert [p.name for p in tmp_path.rglob("*.json")] == ["etc-passwd.json"]
    assert (queries_dir / "etc-passwd.json").exists()


def test_non_sterling_cash_is_left_unvalued(holdings_env, monkeypatch):
    portfolios = [{"owner": "alice", "accounts": [{"holdings": [{"ticker": "CASH.USD", "units": 100}]}]}]
    monkeypatch.setattr(query, "list_portfolios", lambda: portfolios)
    row = query.run_query(_holding_query())["results"][0]
    assert row["market_value_gbp"] is None


def test_get_run_exports_xlsx_attachment(holdings_env):
    resp = make_client().get(
        "/custom-query/run",
        params={
            "start": "2020-01-01",
            "end": "2020-12-31",
            "owners": "bob",
            "metrics": "market_value_gbp",
            "format": "xlsx",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == "attachment; filename=custom-query.xlsx"
    assert b"ABC.L" in zipfile.ZipFile(io.BytesIO(resp.content)).read("xl/worksheets/sheet1.xml")


def test_transfer_in_inside_range_counts_at_that_days_close(holdings_env, monkeypatch):
    # 10 held before the range (1.00), 10 transferred in mid-range with no
    # amount (close that day 2.50), 10 bought after it. The transfer is
    # valued like a buy at that day's close, not at the pooled average.
    portfolios = [
        {
            "owner": "alice",
            "accounts": [
                {"holdings": [{"ticker": "TOP.L", "units": 30, "acquired_date": "2021-03-01", "cost_basis_gbp": 130}]}
            ],
        }
    ]
    tx = [
        {"date": "2019-01-01", "type": "BUY", "ticker": "TOP.L", "units": 10, "amount_minor": 1000},
        {"date": "2020-06-01", "type": "TRANSFER_IN", "ticker": "TOP.L", "units": 10},
        {"date": "2021-03-01", "type": "BUY", "ticker": "TOP.L", "units": 10, "amount_minor": 10000},
    ]
    prices = {("TOP", date(2020, 1, 1)): 1.0, ("TOP", date(2020, 6, 1)): 2.5, ("TOP", date(2020, 12, 31)): 3.0}
    monkeypatch.setattr(query, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(query, "load_transactions", lambda owner: tx)
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (prices.get((sym, d)), None))
    row = query.run_query(_holding_query(metrics=[query.Metric.GAIN_GBP]))["results"][0]
    assert row["start_value_gbp"] == 35.0
    assert row["gain_gbp"] == 25.0


def test_owners_only_per_ticker_query_lists_their_holdings(holdings_env):
    q = query.CustomQuery(start=date(2020, 1, 1), end=date(2020, 12, 31), owners=["bob"])
    assert query._resolve_tickers(q) == ["ABC.L"]


def test_position_sold_out_before_today_has_no_row(holdings_env, monkeypatch):
    # GONE.L was held through 2020 but sold in 2021: no current holding, no row.
    monkeypatch.setattr(
        query,
        "load_transactions",
        lambda owner: [
            {"date": "2019-01-01", "type": "BUY", "ticker": "GONE.L", "units": 5, "amount_minor": 500},
            {"date": "2021-01-01", "type": "SELL", "ticker": "GONE.L", "units": 5},
        ],
    )
    rows = query.run_query(_holding_query(owners=["alice"]))["results"]
    assert "GONE.L" not in {r["ticker"] for r in rows}


def test_past_range_without_a_trusted_replay_is_unknown_not_todays_units(holdings_env):
    # Bob has no transaction history: his units at the end of a past range
    # can't be established, so they and their values are None rather than
    # today's units at a historical price.
    q = _holding_query(owners=["bob"], metrics=[query.Metric.MARKET_VALUE_GBP, query.Metric.GAIN_GBP])
    assert query.run_query(q)["results"] == [
        {
            "owner": "bob",
            "ticker": "ABC.L",
            "units": None,
            "market_value_gbp": None,
            "start_value_gbp": None,
            "gain_gbp": None,
        }
    ]


def test_range_ending_today_without_a_replay_uses_current_units(holdings_env, monkeypatch):
    today = date.today()
    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, d: (3.0, None))
    q = query.CustomQuery(start=date(2020, 1, 1), end=today, owners=["bob"], metrics=[query.Metric.MARKET_VALUE_GBP])
    assert query.run_query(q)["results"][0]["market_value_gbp"] == 3.0
