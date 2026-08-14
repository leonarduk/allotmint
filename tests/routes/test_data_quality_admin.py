"""Route tests for the read-write Data Quality Admin endpoints."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.config import config


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with auth disabled, isolated audit dir, and a writable accounts root."""
    return _build_client(monkeypatch, tmp_path, series=[])


def _build_client(monkeypatch, tmp_path, *, series: list[tuple[str, str, pd.DataFrame]]):
    """Build a TestClient; ``series`` seeds the cached-timeseries aggregation."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "audit_dir", tmp_path / "audit")

    accounts = tmp_path / "accounts"
    (accounts / "demo").mkdir(parents=True)
    (accounts / "demo" / "isa.json").write_text(
        json.dumps(
            {
                "owner": "demo",
                "account_type": "isa",
                "currency": "GBP",
                "holdings": [{"ticker": "MICC.L"}],
            }
        ),
        encoding="utf-8",
    )
    # A writable root distinct from the global demo dataset.
    monkeypatch.setattr(config, "accounts_root", accounts)

    import backend.data_quality.issues as issues_module

    monkeypatch.setattr(
        issues_module,
        "get_instrument_meta",
        lambda ticker: {"name": "MercadoLibre"} if ticker == "MICC.N" else {},
    )
    monkeypatch.setattr(
        issues_module,
        "resolve_instrument_ticker",
        lambda symbol, create_missing=False: "MICC.N" if symbol == "MICC" else None,
    )
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: False)
    monkeypatch.setattr(
        issues_module, "list_cached_meta_tickers", lambda: [(t, e) for t, e, _ in series]
    )
    monkeypatch.setattr(
        issues_module,
        "load_cached_meta_timeseries_full",
        lambda t, e: next((df.copy() for st, se, df in series if st == t and se == e), None),
    )

    # Point the app's accounts store at the writable root so holding writes are allowed.
    from backend.app import create_app

    app = create_app()
    app.state.accounts_root = str(accounts)
    app.state.accounts_root_is_global = False
    return TestClient(app)



def test_get_issues_lists_wrong_exchange(client):
    resp = client.get("/data-quality/issues")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    wrong = [i for i in data["issues"] if i["type"] == "WRONG_EXCHANGE"]
    assert wrong
    assert wrong[0]["entity"]["holding"] == "MICC.L"
    assert wrong[0]["preview"]["after"] == {"ticker": "MICC.N"}


def test_get_issues_filters_by_type(client):
    resp = client.get("/data-quality/issues?type=WRONG_EXCHANGE")
    assert resp.status_code == 200
    assert all(i["type"] == "WRONG_EXCHANGE" for i in resp.json()["issues"])


def test_preview_issue(client):
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")
    resp = client.get(f"/data-quality/issues/{wrong['id']}/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == wrong["id"]
    assert data["fixable"] is True


def test_preview_unknown_issue_404(client):
    resp = client.get("/data-quality/issues/nope/preview")
    assert resp.status_code == 404


def test_fix_wrong_exchange_writes_holding_and_audit(client, tmp_path):
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")

    resp = client.post(f"/data-quality/issues/{wrong['id']}/fix")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "MICC.N"

    account_path = tmp_path / "accounts" / "demo" / "isa.json"
    doc = json.loads(account_path.read_text(encoding="utf-8"))
    assert doc["holdings"] == [{"ticker": "MICC.N"}]
    # .bak backup preserved the pre-fix state.
    assert (tmp_path / "accounts" / "demo" / "isa.json.bak").exists()

    audit = client.get("/data-quality/audit").json()["entries"]
    assert audit
    assert audit[0]["action"] == "wrong_exchange"
    assert audit[0]["before"] == {"holdings": [{"ticker": "MICC.L"}]}


def test_fix_unknown_issue_404(client):
    resp = client.post("/data-quality/issues/nope/fix")
    assert resp.status_code == 404


def test_batch_fix_reports_per_issue(client):
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = [i for i in issues if i["type"] == "WRONG_EXCHANGE"]
    ids = [i["id"] for i in wrong]
    resp = client.post("/data-quality/fixes", json={"issue_ids": ids})
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] == len(ids)
    assert data["failed"] == 0
    assert all(r["status"] == "ok" for r in data["results"])


def test_batch_fix_reports_failures(client):
    resp = client.post(
        "/data-quality/fixes",
        json={"issue_ids": ["WRONG_EXCHANGE:demo:isa:MICC.L", "not-a-real-id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] == 1
    assert data["failed"] == 1
    failed = next(r for r in data["results"] if r["issue_id"] == "not-a-real-id")
    assert failed["status"] == "error"


def test_dedupe_series_direct_endpoint(monkeypatch, client, tmp_path):
    df = pd.DataFrame(
        {"Date": ["2026-01-01", "2026-01-01", "2026-01-02"], "Close": [1.0, 2.0, 3.0]}
    )
    cache_path = tmp_path / "ABC_L.parquet"
    df.to_parquet(cache_path, index=False)

    import backend.routes.data_quality_admin as admin_module

    monkeypatch.setattr(admin_module, "meta_timeseries_cache_path", lambda t, e: str(cache_path))
    monkeypatch.setattr(admin_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())

    resp = client.post("/data-quality/series/ABC/L/dedupe")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1
    assert cache_path.with_suffix(".parquet.bak").exists()

    audit = client.get("/data-quality/audit").json()["entries"]
    assert audit[0]["action"] == "dedupe"
    assert audit[0]["before"] == {"rows": 3}
    assert audit[0]["after"] == {"rows": 2}


def test_audit_undo_wrong_exchange(client, tmp_path):
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")
    client.post(f"/data-quality/issues/{wrong['id']}/fix")

    audit = client.get("/data-quality/audit").json()["entries"]
    entry_id = audit[0]["id"]

    resp = client.post(f"/data-quality/audit/{entry_id}/undo")
    assert resp.status_code == 200
    assert resp.json()["status"] == "undone"

    doc = json.loads((tmp_path / "accounts" / "demo" / "isa.json").read_text(encoding="utf-8"))
    assert doc["holdings"] == [{"ticker": "MICC.L"}]


def test_audit_undo_non_reversible_409(client):
    # A refetch action is not reversible; manufacture one via the audit file.
    import backend.data_quality.audit as audit_module

    entry = audit_module.append_audit(
        action="refetch",
        issue_id="GAPS:ABC:L",
        entity={"ticker": "ABC", "exchange": "L"},
        before={},
        after={"rows": 5},
    )
    resp = client.post(f"/data-quality/audit/{entry['id']}/undo")
    assert resp.status_code == 409


def test_audit_undo_unknown_404(client):
    resp = client.post("/data-quality/audit/missing/undo")
    assert resp.status_code == 404


def test_outliers_not_fixable(monkeypatch, tmp_path):
    """OUTLIERS issues report fixable=False and the fix endpoint rejects them."""
    dates = [f"2026-01-{d:02d}" for d in range(3, 25)]
    closes = [100.0 + i for i in range(len(dates))]
    closes[10] = 500.0
    df = pd.DataFrame({"Date": dates, "Close": closes, "Ticker": ["ABC"] * len(dates)})

    outlier_client = _build_client(monkeypatch, tmp_path, series=[("ABC", "L", df)])
    issues = outlier_client.get("/data-quality/issues").json()["issues"]
    outliers = [i for i in issues if i["type"] == "OUTLIERS"]
    assert outliers
    assert outliers[0]["fixable"] is False
    resp = outlier_client.post(f"/data-quality/issues/{outliers[0]['id']}/fix")
    assert resp.status_code == 409

