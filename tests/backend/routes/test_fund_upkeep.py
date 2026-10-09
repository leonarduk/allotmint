"""Fund upkeep routes (#10482): approval is the only write, and it is audited and undoable."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.fund_upkeep as routes
from backend.common import instruments
from backend.common.fund_charges import ongoing_charge_pct
from backend.config import config
from backend.data_quality.audit import read_audit
from backend.fund_upkeep import proposals
from tests.backend.fund_upkeep.fixtures import make_catalogue, stored_meta

DOC_URL = "https://issuer.example.com/docs/fundx-kiid.pdf"


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = make_catalogue(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "disable_auth", True)
    app = FastAPI()
    app.include_router(routes.router)
    yield TestClient(app), root
    instruments.get_instrument_meta.cache_clear()


def _queue(value=0.22):
    raw = {"ticker": "FUNDX.L", "ongoing_charge_pct": value, "source_url": DOC_URL, "document_date": "2026-09-01"}
    return proposals.add_proposal(proposals.validate_charge(raw, today=date(2026, 10, 9)))


def test_approve_writes_metadata_with_audit_and_charges_view_counts_it(client):
    http, root = client
    proposal = _queue()
    assert ongoing_charge_pct(instruments.get_instrument_meta("FUNDX.L")) is None

    response = http.post(f"/fund-upkeep/proposals/{proposal['id']}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    meta = stored_meta(root)
    assert meta["ongoing_charge_pct"] == 0.22
    assert meta["ongoing_charge_source"] == {"url": DOC_URL, "document_date": "2026-09-01"}
    assert meta["name"] == "Example Global Fund"  # merge, not replace
    assert ongoing_charge_pct(instruments.get_instrument_meta("FUNDX.L")) == 0.22
    entry = read_audit()[0]
    assert entry["id"] == response.json()["audit_id"]
    assert entry["action"] == "fund_upkeep_approve"
    assert entry["before"] == {"ongoing_charge_pct": None, "ongoing_charge_source": None}
    assert entry["extra"] == {"source_url": DOC_URL, "document_date": "2026-09-01"}


def test_undo_restores_previous_values(client):
    http, root = client
    proposal = _queue()
    http.post(f"/fund-upkeep/proposals/{proposal['id']}/approve")

    response = http.post(f"/fund-upkeep/proposals/{proposal['id']}/undo")

    assert response.status_code == 200
    assert response.json()["status"] == "undone"
    assert ongoing_charge_pct(stored_meta(root)) is None
    assert [e["action"] for e in read_audit()] == ["fund_upkeep_undo", "fund_upkeep_approve"]


def test_undo_refuses_when_metadata_changed_since(client):
    http, _root = client
    proposal = _queue()
    http.post(f"/fund-upkeep/proposals/{proposal['id']}/approve")
    instruments.save_instrument_meta(
        "FUNDX.L", {**instruments.get_instrument_meta("FUNDX.L"), "ongoing_charge_pct": 0.3}
    )

    response = http.post(f"/fund-upkeep/proposals/{proposal['id']}/undo")

    assert response.status_code == 409


def test_reject_writes_nothing_and_decided_proposals_cannot_be_approved(client):
    http, root = client
    proposal = _queue()

    assert http.post(f"/fund-upkeep/proposals/{proposal['id']}/reject").json()["status"] == "rejected"
    assert http.post(f"/fund-upkeep/proposals/{proposal['id']}/approve").status_code == 409
    assert "ongoing_charge_pct" not in stored_meta(root)
    assert read_audit() == []
    assert http.post("/fund-upkeep/proposals/no-such-id/approve").status_code == 404


def test_implausible_or_unsourced_values_are_never_queued(client):
    with pytest.raises(proposals.ProposalRejected):
        _queue(value=22)
    with pytest.raises(proposals.ProposalRejected):
        proposals.validate_charge({"ticker": "FUNDX.L", "ongoing_charge_pct": 0.2, "document_date": "2026-09-01"})
    assert client[0].get("/fund-upkeep/proposals").json() == []


def test_list_proposals_filters_by_status(client):
    http, _root = client
    _queue()

    assert len(http.get("/fund-upkeep/proposals", params={"status": "pending"}).json()) == 1
    assert http.get("/fund-upkeep/proposals", params={"status": "approved"}).json() == []
    assert http.get("/fund-upkeep/proposals", params={"status": "bogus"}).status_code == 422


def test_all_in_cost_route_reads_holdings_and_owner_transactions(client, monkeypatch):
    http, _root = client
    portfolio = {
        "accounts": [
            {
                "account_type": "ISA",
                "holdings": [{"ticker": "FUNDX.L", "market_value_gbp": 1000.0, "ongoing_charge_pct": 0.5}],
            }
        ]
    }
    monkeypatch.setattr(routes, "resolve_owner_directory", lambda _root, _owner: None)
    monkeypatch.setattr(routes.portfolio_mod, "build_owner_portfolio", lambda owner, root: portfolio)
    monkeypatch.setattr(routes, "resolve_writable_store", lambda _request: (None, None))
    txs = [
        SimpleNamespace(
            owner="alex",
            model_dump=lambda: {"account": "isa", "type": "BUY", "date": date.today().isoformat(), "fees": 5.0},
        ),
        SimpleNamespace(
            owner="sam",
            model_dump=lambda: {"account": "isa", "type": "BUY", "date": date.today().isoformat(), "fees": 99.0},
        ),
    ]
    monkeypatch.setattr(routes, "load_all_transactions", lambda _store: txs)

    body = http.get("/fund-upkeep/alex/all-in-cost").json()

    assert body["total"]["fund_charges_gbp"] == 5.0
    assert body["total"]["dealing_fees_gbp"] == 5.0
    assert body["total"]["known_cost_gbp"] == 10.0
