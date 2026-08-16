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
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [(t, e) for t, e, _ in series])
    monkeypatch.setattr(
        issues_module,
        "load_cached_meta_timeseries_full",
        lambda t, e: next((df.copy() for st, se, df in series if st == t and se == e), None),
    )

    # Point the app's accounts store at the writable root so holding writes are allowed.
    from backend.app import create_app

    app = create_app()
    # ``create_app`` reloads the configuration (``reload_config``), which resets
    # the audit_dir patch above; re-apply it so the audit trail stays inside
    # this test's tmp dir instead of the real data root.
    monkeypatch.setattr(config, "audit_dir", tmp_path / "audit")
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


def test_fix_missing_series_dispatches_to_refetch(monkeypatch, client, tmp_path):
    """MISSING_SERIES issues carry kind='missing_series' and must dispatch to
    the refetch fix rather than falling through to 409 (regression for #6727)."""
    import backend.data_quality.issues as issues_module
    import backend.routes.data_quality_admin as admin_module

    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "MercadoLibre"})
    monkeypatch.setattr(
        issues_module,
        "resolve_instrument_ticker",
        lambda symbol, create_missing=False: f"{symbol}.L",
    )
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: False)

    cache_path = tmp_path / "MICC_L.parquet"
    monkeypatch.setattr(admin_module, "meta_timeseries_cache_path", lambda t, e: str(cache_path))
    fresh = pd.DataFrame({"Date": ["2026-01-01"], "Close": [1.0]})
    monkeypatch.setattr(admin_module, "load_meta_timeseries", lambda t, e, days: fresh.copy())

    issues = client.get("/data-quality/issues").json()["issues"]
    missing = next(i for i in issues if i["type"] == "MISSING_SERIES")

    resp = client.post(f"/data-quality/issues/{missing['id']}/fix")
    assert resp.status_code == 200
    assert resp.json()["rows"] == 1


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


def test_batch_fix_aggregates_issues_once_for_whole_batch(monkeypatch, client):
    """Regression for #6741: batch fix must scan once, not once per issue id."""
    import backend.routes.data_quality_admin as admin_module

    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = [i for i in issues if i["type"] == "WRONG_EXCHANGE"]
    ids = [i["id"] for i in wrong]
    assert ids

    calls = []
    real_aggregate_issues = admin_module.aggregate_issues

    def counting_aggregate_issues(*args, **kwargs):
        calls.append(1)
        return real_aggregate_issues(*args, **kwargs)

    monkeypatch.setattr(admin_module, "aggregate_issues", counting_aggregate_issues)

    resp = client.post("/data-quality/fixes", json={"issue_ids": ids})
    assert resp.status_code == 200
    assert len(calls) == 1


def test_batch_fix_skips_issue_resolved_earlier_in_same_batch(client):
    """An issue id repeated in the batch is only applied once; the second
    occurrence is revalidated against the live holding and skipped rather
    than reapplied, since the first fix already changed it (#6741)."""
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")

    resp = client.post("/data-quality/fixes", json={"issue_ids": [wrong["id"], wrong["id"]]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] == 1
    assert data["failed"] == 1
    second = data["results"][1]
    assert second["status"] == "error"
    assert "no longer applies" in second["detail"]


def test_dedupe_series_direct_endpoint(monkeypatch, client, tmp_path):
    df = pd.DataFrame({"Date": ["2026-01-01", "2026-01-01", "2026-01-02"], "Close": [1.0, 2.0, 3.0]})
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


def test_audit_undo_restores_correct_holding_after_list_change(client, tmp_path):
    """Undo must not misalign when other holdings changed since the fix."""
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")
    client.post(f"/data-quality/issues/{wrong['id']}/fix")

    audit = client.get("/data-quality/audit").json()["entries"]
    entry_id = audit[0]["id"]

    # Simulate a later unrelated change: reorder holdings and add a new one.
    account_path = tmp_path / "accounts" / "demo" / "isa.json"
    doc = json.loads(account_path.read_text(encoding="utf-8"))
    doc["holdings"] = [{"ticker": "NEW.H"}, {"ticker": "MICC.N"}]
    account_path.write_text(json.dumps(doc), encoding="utf-8")

    resp = client.post(f"/data-quality/audit/{entry_id}/undo")
    assert resp.status_code == 200

    doc = json.loads(account_path.read_text(encoding="utf-8"))
    # Only the fixed holding is reverted; the unrelated holding stays.
    assert doc["holdings"] == [{"ticker": "NEW.H"}, {"ticker": "MICC.L"}]


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


def test_dedupe_series_rejects_path_traversal(monkeypatch, client, tmp_path):
    """Cache keys from the URL must never escape the cache base (CodeQL)."""
    import backend.routes.data_quality_admin as admin_module

    # Hermetic: point the cache at a temp dir so the valid-key case never
    # touches real repo/demo cache data.
    monkeypatch.setattr(admin_module, "meta_timeseries_cache_path", lambda t, e: str(tmp_path / f"{t}_{e}.parquet"))
    # Encoded path separators are rejected by the router itself (404, never
    # reaching the handler); other invalid characters are rejected by
    # ``_validate_cache_key`` (400).  Either way the key is never used to
    # build a filesystem path.
    resp = client.post("/data-quality/series/..%2F..%2Fetc%2Fpasswd/L/dedupe")
    assert resp.status_code in (400, 404)
    resp = client.post("/data-quality/series/ABC/..%2F..%2Fetc/dedupe")
    assert resp.status_code in (400, 404)
    # Characters outside the ticker charset are rejected by validation.
    resp = client.post("/data-quality/series/BAD%20TICKER/L/dedupe")
    assert resp.status_code == 400
    # A plain valid key passes validation and reports the missing file.
    resp = client.post("/data-quality/series/ABC/L/dedupe")
    assert resp.status_code == 404


def test_undo_rejects_traversal_owner(client):
    """Owner/account from the audit entry are path components; escapes are rejected."""
    import backend.data_quality.audit as audit_module

    entry = audit_module.append_audit(
        action="wrong_exchange",
        issue_id="WRONG_EXCHANGE:evil:isa:MICC.L",
        entity={"owner": "../../evil", "account": "isa"},
        before={"holdings": [{"ticker": "MICC.L"}]},
        after={"holdings": [{"ticker": "MICC.N"}]},
        extra={"kind": "wrong_exchange", "owner": "../../evil", "account": "isa"},
    )
    resp = client.post(f"/data-quality/audit/{entry['id']}/undo")
    assert resp.status_code == 400

    entry = audit_module.append_audit(
        action="dedupe",
        issue_id="DUPLICATES:ABC:L",
        entity={"ticker": "ABC", "exchange": "L"},
        before={"rows": 3},
        after={"rows": 2},
        extra={"kind": "dedupe", "ticker": "..", "exchange": "L"},
    )
    resp = client.post(f"/data-quality/audit/{entry['id']}/undo")
    assert resp.status_code == 400


def test_fix_wrong_exchange_rolls_back_when_audit_fails(monkeypatch, client, tmp_path):
    """A failed audit write must restore the pre-fix holdings document."""
    import backend.data_quality.audit as audit_module

    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")

    def failing_append(path, line):
        raise OSError("simulated audit disk failure")

    monkeypatch.setattr(audit_module, "_atomic_append_text", failing_append)

    with pytest.raises(OSError):
        client.post(f"/data-quality/issues/{wrong['id']}/fix")

    account_path = tmp_path / "accounts" / "demo" / "isa.json"
    doc = json.loads(account_path.read_text(encoding="utf-8"))
    assert doc["holdings"] == [{"ticker": "MICC.L"}]  # rolled back, not MICC.N


def test_undo_skips_holding_edited_since_fix(client, tmp_path):
    """Undo must not overwrite a holding that changed after the fix."""
    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")
    client.post(f"/data-quality/issues/{wrong['id']}/fix")

    audit = client.get("/data-quality/audit").json()["entries"]
    entry_id = audit[0]["id"]

    # Simulate a later manual edit: same ticker, different quantity.
    account_path = tmp_path / "accounts" / "demo" / "isa.json"
    doc = json.loads(account_path.read_text(encoding="utf-8"))
    doc["holdings"] = [{"ticker": "MICC.N", "qty": 999}]
    account_path.write_text(json.dumps(doc), encoding="utf-8")

    resp = client.post(f"/data-quality/audit/{entry_id}/undo")
    assert resp.status_code == 200

    doc = json.loads(account_path.read_text(encoding="utf-8"))
    # The manually edited holding is left untouched (no stale-snapshot clobber).
    assert doc["holdings"] == [{"ticker": "MICC.N", "qty": 999}]


def test_fix_wrong_exchange_rollback_preserves_concurrent_edit(monkeypatch, client, tmp_path):
    """A failed audit write must not clobber a concurrent edit made after the fix."""
    import backend.routes.data_quality_admin as admin_module

    issues = client.get("/data-quality/issues").json()["issues"]
    wrong = next(i for i in issues if i["type"] == "WRONG_EXCHANGE")
    account_path = tmp_path / "accounts" / "demo" / "isa.json"

    def failing_append_after_concurrent_edit(**kwargs):
        # Simulate another request landing between the fix write and the
        # audit write: it edits the same document on top of our change.
        doc = json.loads(account_path.read_text(encoding="utf-8"))
        doc["holdings"] = [{"ticker": "MICC.N", "qty": 999}]
        account_path.write_text(json.dumps(doc), encoding="utf-8")
        raise OSError("simulated audit disk failure")

    monkeypatch.setattr(admin_module, "append_audit", failing_append_after_concurrent_edit)

    with pytest.raises(OSError):
        client.post(f"/data-quality/issues/{wrong['id']}/fix")

    doc = json.loads(account_path.read_text(encoding="utf-8"))
    # The concurrent edit survives: the rollback must not restore the .bak
    # over a file that changed since this fix wrote it.
    assert doc["holdings"] == [{"ticker": "MICC.N", "qty": 999}]


def _gapped_series_client(monkeypatch, tmp_path):
    """Client whose cached series ABC.L has a 4-business-day gap (GAPS issue)."""
    df = pd.DataFrame({"Date": ["2026-01-05", "2026-01-12"], "Close": [1.0, 2.0]})
    client = _build_client(monkeypatch, tmp_path, series=[("ABC", "L", df)])
    import backend.routes.data_quality_admin as admin_module

    cache_path = tmp_path / "ABC_L.parquet"
    df.to_parquet(cache_path, index=False)
    monkeypatch.setattr(admin_module, "meta_timeseries_cache_path", lambda t, e: str(cache_path))
    return client, cache_path, admin_module


def test_fix_refetch_rejects_empty_fetch(monkeypatch, tmp_path):
    """An empty upstream fetch must fail without auditing or touching the cache."""
    client, cache_path, admin_module = _gapped_series_client(monkeypatch, tmp_path)
    before_bytes = cache_path.read_bytes()
    monkeypatch.setattr(admin_module, "load_meta_timeseries", lambda t, e, days: pd.DataFrame(columns=["Date"]))

    issues = client.get("/data-quality/issues").json()["issues"]
    gaps = [i for i in issues if i["type"] == "GAPS"]
    assert gaps

    resp = client.post(f"/data-quality/issues/{gaps[0]['id']}/fix")
    assert resp.status_code == 502
    assert "no valid data" in resp.json()["detail"]

    audit = client.get("/data-quality/audit").json()["entries"]
    assert all(e["action"] != "refetch" for e in audit)
    assert cache_path.read_bytes() == before_bytes


def test_fix_refetch_records_before_rows(monkeypatch, tmp_path):
    """A successful refetch audits the real pre-fix row count, not None."""
    client, cache_path, admin_module = _gapped_series_client(monkeypatch, tmp_path)
    fresh = pd.DataFrame({"Date": ["2026-01-05", "2026-01-06", "2026-01-12"], "Close": [1.0, 1.5, 2.0]})
    monkeypatch.setattr(admin_module, "load_meta_timeseries", lambda t, e, days: fresh.copy())

    issues = client.get("/data-quality/issues").json()["issues"]
    gaps = [i for i in issues if i["type"] == "GAPS"]
    resp = client.post(f"/data-quality/issues/{gaps[0]['id']}/fix")
    assert resp.status_code == 200
    assert resp.json()["rows"] == 3

    audit = client.get("/data-quality/audit").json()["entries"]
    assert audit[0]["action"] == "refetch"
    assert audit[0]["before"] == {"rows": 2}
    assert audit[0]["after"] == {"rows": 3}


def test_dedupe_handles_timezone_aware_dates(monkeypatch, client, tmp_path):
    """Dedupe normalises tz-aware Date values before comparing/sorting."""
    import backend.routes.data_quality_admin as admin_module

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"], utc=True),
            "Close": [1.0, 2.0, 3.0],
        }
    )
    cache_path = tmp_path / "ABC_L.parquet"
    df.to_parquet(cache_path, index=False)
    monkeypatch.setattr(admin_module, "meta_timeseries_cache_path", lambda t, e: str(cache_path))
    monkeypatch.setattr(admin_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())

    resp = client.post("/data-quality/series/ABC/L/dedupe")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1
    assert resp.json()["rows"] == 2

    written = pd.read_parquet(cache_path)
    # The written cache follows the tz-naive datetime64[ms] convention.
    assert written["Date"].dt.tz is None
    assert len(written) == 2


def test_dedupe_rejects_series_with_no_valid_dates(monkeypatch, client, tmp_path):
    """A cache whose dates are all unparseable is rejected, not emptied."""
    import backend.routes.data_quality_admin as admin_module

    df = pd.DataFrame({"Date": ["not-a-date", "also-not-a-date"], "Close": [1.0, 2.0]})
    cache_path = tmp_path / "ABC_L.parquet"
    df.to_parquet(cache_path, index=False)
    before_bytes = cache_path.read_bytes()
    monkeypatch.setattr(admin_module, "meta_timeseries_cache_path", lambda t, e: str(cache_path))
    monkeypatch.setattr(admin_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())

    resp = client.post("/data-quality/series/ABC/L/dedupe")
    assert resp.status_code == 502
    assert cache_path.read_bytes() == before_bytes
    audit = client.get("/data-quality/audit").json()["entries"]
    assert all(e["action"] != "dedupe" for e in audit)
