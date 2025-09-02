import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.approvals import load_approvals, save_approvals

from backend.common.compliance import check_owner
from backend.common.holding_utils import enrich_holding
from backend.config import config


def test_enrich_holding_requires_approval(monkeypatch):
    today = date(2024, 5, 8)
    acq = (today - timedelta(days=config.hold_days_min + 1)).isoformat()
    holding = {
        "ticker": "ADM.L",
        "acquired_date": acq,
        "units": 1,
        "cost_basis_gbp": 1.0,
    }
    monkeypatch.setattr(
        "backend.common.holding_utils._get_price_for_date_scaled",
        lambda *a, **k: (1.0, None),
    )
    out = enrich_holding(holding, today, {}, {})
    assert out["sell_eligible"] is False
    expect_date = (date.fromisoformat(acq) + timedelta(days=config.hold_days_min)).isoformat()
    assert out["next_eligible_sell_date"] == expect_date

    approvals = {"ADM.L": today}
    out = enrich_holding(holding, today, {}, approvals)
    assert out["sell_eligible"] is True


def test_compliance_checks_approval(monkeypatch, tmp_path):
    owner_dir = tmp_path / "bob"
    owner_dir.mkdir()
    txs = {
        "account_type": "ISA",
        "transactions": [
            {"date": "2024-05-01", "ticker": "ADM.L", "type": "buy"},
            {"date": "2024-06-05", "ticker": "ADM.L", "type": "sell"},
        ],
    }
    (owner_dir / "isa_transactions.json").write_text(json.dumps(txs))

    res = check_owner("bob", accounts_root=tmp_path)
    assert any("without approval" in w.lower() for w in res["warnings"])

    approvals = {"approvals": [{"ticker": "ADM.L", "approved_on": "2024-06-04"}]}
    (owner_dir / "approvals.json").write_text(json.dumps(approvals))
    res = check_owner("bob", accounts_root=tmp_path)
    assert not any("without approval" in w.lower() for w in res["warnings"])


def test_save_approvals_persists(tmp_path):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    approvals = {"ABC": date(2024, 6, 1)}
    save_approvals("alice", approvals, accounts_root=tmp_path)
    data = json.loads((owner_dir / "approvals.json").read_text())
    assert data["approvals"][0]["ticker"] == "ABC"
    loaded = load_approvals("alice", accounts_root=tmp_path)
    assert loaded == approvals


def test_approvals_endpoints(tmp_path):
    owner_dir = tmp_path / "bob"
    owner_dir.mkdir()
    old_root = config.accounts_root
    old_skip = config.skip_snapshot_warm
    old_offline = config.offline_mode
    config.accounts_root = tmp_path
    config.skip_snapshot_warm = True
    config.offline_mode = True
    app = create_app()
    client = TestClient(app)
    try:
        resp = client.get("/accounts/bob/approvals")
        assert resp.status_code == 200
        assert resp.json() == {"approvals": []}

        resp = client.post(
            "/accounts/bob/approvals",
            json={"ticker": "ADM.L", "approved_on": "2024-06-04"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approvals"][0]["ticker"] == "ADM.L"

        resp = client.request(
            "DELETE", "/accounts/bob/approvals", json={"ticker": "ADM.L"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"approvals": []}
    finally:
        config.accounts_root = old_root
        config.skip_snapshot_warm = old_skip
        config.offline_mode = old_offline
