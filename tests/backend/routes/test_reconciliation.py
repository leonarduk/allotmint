"""POST /reconciliation/statement (#10474): read-only, with the LLM mocked."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import get_active_user
from backend.common import accounts_store
from backend.reconciliation import extract
from backend.routes import reconciliation, transactions

# A synthetic quarter (not a real statement): a deposit, a BUY with an £11.95
# fee and £2.50 of interest, closing with £3,990.55 cash.
EXTRACTION = {
    "document_type": "statement",
    "period_start": "2026-01-01",
    "period_end": "2026-03-31",
    "opening_cash": 0,
    "closing_cash": 3990.55,
    "rows": [
        {"date": "2026-01-05", "type": "DEPOSIT", "description": "Debit card", "amount": 5000},
        {
            "date": "2026-01-10",
            "type": "BUY",
            "description": "BP PLC",
            "ticker": "BP.L",
            "units": 200,
            "price": 500,
            "price_unit": "GBX",
            "consideration": 1000,
            "fees": 11.95,
            "amount": 1011.95,
        },
        {"date": "2026-03-31", "type": "INTEREST", "description": "Interest", "amount": 2.50},
    ],
    "closing_holdings": [{"ticker": "BP.L", "units": 200}],
}

# The ledger is missing the interest and recorded the BUY with no fee.
LEDGER = {
    "owner": "alice",
    "account_type": "isa",
    "trade_cash_effects": True,
    "transactions": [
        {"date": "2026-01-05", "type": "DEPOSIT", "amount_minor": 500000},
        {
            "date": "2026-01-10",
            "type": "BUY",
            "ticker": "BP.L",
            "units": 200,
            "price_gbp": 5.0,
            "fees": 0,
            "reason": "Income",
        },
    ],
}

STATEMENT_CSV = b"Synthetic statement fixture\nDate,Description,Amount\n"


@pytest.fixture
def client(monkeypatch, tmp_path):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "isa_transactions.json").write_text(json.dumps(LEDGER), encoding="utf-8")

    app = FastAPI()
    app.include_router(transactions.router)
    app.include_router(reconciliation.router)
    app.dependency_overrides[get_active_user] = lambda: None
    app.state.accounts_root = tmp_path
    app.state.accounts_root_is_global = False
    monkeypatch.setattr(
        transactions,
        "config",
        SimpleNamespace(accounts_root=tmp_path, repo_root=None, offline_mode=False, app_env="local"),
    )
    monkeypatch.setattr(
        reconciliation,
        "config",
        SimpleNamespace(chat_provider="ollama", app_env="local", mcp_server_url="http://mcp.test"),
    )
    monkeypatch.setattr(reconciliation, "ensure_owner_access", lambda *a, **k: None)
    monkeypatch.setattr(reconciliation, "get_instrument_meta", lambda ticker: {})
    monkeypatch.setattr(
        accounts_store, "portfolio_loader", SimpleNamespace(rebuild_account_holdings=lambda *a, **k: None)
    )
    monkeypatch.setattr(accounts_store, "portfolio_mod", SimpleNamespace(build_owner_portfolio=lambda *a, **k: None))
    monkeypatch.setattr(accounts_store, "_lock_file", lambda f: None)
    monkeypatch.setattr(accounts_store, "_unlock_file", lambda f: None)
    transactions._POSTED_TRANSACTIONS.clear()

    async def fake_complete(text, cfg):
        return json.dumps(EXTRACTION)

    monkeypatch.setattr(extract, "complete_extraction", fake_complete)
    return TestClient(app)


def _post_statement(client, **data):
    return client.post(
        "/reconciliation/statement",
        data={"owner": "alice", "account": "isa", **data},
        files={"file": ("statement.csv", STATEMENT_CSV, "text/csv")},
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_reports_missing_interest_fee_and_cash(client):
    resp = _post_statement(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_provider"] == "ollama" and body["sent_to_cloud"] is False
    kinds = sorted(d["kind"] for d in body["diffs"])
    assert kinds == ["cash_mismatch", "fee_mismatch", "missing_from_ledger"]
    cash = next(d for d in body["diffs"] if d["kind"] == "cash_mismatch")
    # Ledger: £5,000 deposit - £1,000 BUY (no fee) = £4,000; statement £3,990.55.
    assert cash["ledger_minor"] == 400_000 and cash["statement_minor"] == 399_055
    assert cash["difference_minor"] == -945
    assert "-£9.45" in cash["message"]
    assert [m["statement_index"] for m in body["matched"]] == [0]


def test_reconcile_does_not_write_to_the_store(client, tmp_path):
    before = _snapshot(tmp_path)

    assert _post_statement(client).status_code == 200

    assert _snapshot(tmp_path) == before
    assert transactions._POSTED_TRANSACTIONS == []


def test_accepting_suggestions_through_transactions_endpoints_reconciles(client):
    diffs = _post_statement(client).json()["diffs"]

    for diff in diffs:
        request = diff["suggestion"]["request"]
        if request is None:
            continue
        resp = client.request(request["method"], request["path"], json=request["body"])
        assert resp.status_code in (200, 201), resp.text

    rerun = _post_statement(client).json()
    assert rerun["diffs"] == []
    assert len(rerun["matched"]) == 3


def test_scanned_pdf_is_rejected_as_unsupported(client, monkeypatch):
    monkeypatch.setattr(
        extract,
        "extract_document_text",
        lambda data, name: (_ for _ in ()).throw(extract.UnsupportedDocument("scanned")),
    )

    resp = _post_statement(client)

    assert resp.status_code == 415


def test_invalid_model_output_is_a_422(client, monkeypatch):
    async def bad_complete(text, cfg):
        return "not json"

    monkeypatch.setattr(extract, "complete_extraction", bad_complete)

    assert _post_statement(client).status_code == 422


def test_llm_failure_is_a_502(client, monkeypatch):
    async def failing(text, cfg):
        raise ConnectionError("down")

    monkeypatch.setattr(extract, "complete_extraction", failing)

    assert _post_statement(client).status_code == 502


def test_invalid_owner_is_rejected(client):
    resp = client.post(
        "/reconciliation/statement",
        data={"owner": "../alice", "account": "isa"},
        files={"file": ("s.csv", STATEMENT_CSV, "text/csv")},
    )

    assert resp.status_code == 400


def test_oversized_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(reconciliation, "MAX_UPLOAD_BYTES", 10)

    assert _post_statement(client).status_code == 413


def test_explain_unmatched_attaches_agent_reply(client, monkeypatch):
    seen = {}

    async def fake_turn(message, history, **kwargs):
        seen["message"] = message
        seen["system_prompt"] = kwargs["system_prompt"]
        return "Fee probably not entered."

    monkeypatch.setattr(reconciliation.explain, "run_configured_chat_turn", fake_turn)

    body = _post_statement(client, explain_unmatched="true").json()

    assert body["explanation"] == "Fee probably not entered."
    assert "fee_mismatch" in seen["message"] and "cash_mismatch" not in seen["message"]
    assert "investment advice" in seen["system_prompt"]


def test_explain_failure_becomes_a_warning(client, monkeypatch):
    async def failing_turn(*args, **kwargs):
        raise RuntimeError("model offline")

    monkeypatch.setattr(reconciliation.explain, "run_configured_chat_turn", failing_turn)

    body = _post_statement(client, explain_unmatched="true").json()

    assert body["explanation"] is None
    assert any("could not be explained" in w for w in body["warnings"])


def test_provider_endpoint_reports_cloud_use(client, monkeypatch):
    monkeypatch.setattr(reconciliation, "config", SimpleNamespace(chat_provider="bedrock", app_env="aws"))

    assert client.get("/reconciliation/provider").json() == {"llm_provider": "bedrock", "sent_to_cloud": True}


def test_create_cash_transaction_requires_amount(client):
    resp = client.post(
        "/transactions",
        json={"owner": "alice", "account": "isa", "date": "2026-02-01", "type": "INTEREST", "reason": "x"},
    )

    assert resp.status_code == 400
    assert "amount_minor" in resp.json()["detail"]


def test_create_trade_still_requires_ticker(client):
    resp = client.post(
        "/transactions",
        json={
            "owner": "alice",
            "account": "isa",
            "date": "2026-02-01",
            "type": "BUY",
            "price_gbp": 1,
            "units": 1,
            "reason": "x",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "ticker is required"


def test_created_cash_row_stores_no_trade_fields(client, tmp_path):
    resp = client.post(
        "/transactions",
        json={
            "owner": "alice",
            "account": "isa",
            "date": "2026-02-01",
            "type": "INTEREST",
            "amount_minor": 250,
            "reason": "x",
        },
    )

    assert resp.status_code == 201
    stored = json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"][-1]
    assert stored == {
        "date": "2026-02-01",
        "type": "INTEREST",
        "amount_minor": 250,
        "comments": None,
        "reason": "x",
        "external_id": None,
    }
