import json
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import compliance


def _setup_app(tmp_path):
    accounts = tmp_path / "accounts" / "alice"
    accounts.mkdir(parents=True)
    data = {
        "account_type": "brokerage",
        "transactions": [
            {"date": "2024-01-01", "ticker": "AAA", "type": "buy", "shares": 10}
        ],
    }
    (accounts / "alice_transactions.json").write_text(json.dumps(data))
    app = create_app()
    app.state.accounts_root = accounts.parent
    return app


def test_compliance_owner_route(tmp_path):
    app = _setup_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/compliance/alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["owner"] == "alice"
        assert data["warnings"] == []


def test_validate_trade(tmp_path, monkeypatch):
    app = _setup_app(tmp_path)
    monkeypatch.setattr(
        "backend.common.compliance.get_instrument_meta", lambda t: {"instrumentType": "ETF"}
    )
    monkeypatch.setattr(compliance.config, "approval_exempt_types", ["ETF"])
    with TestClient(app) as client:
        resp = client.post(
            "/compliance/validate",
            json={
                "owner": "alice",
                "account": "brokerage",
                "date": "2024-01-10",
                "type": "sell",
                "ticker": "AAA",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any("Sold AAA" in w for w in data["warnings"])

        resp2 = client.post(
            "/compliance/validate",
            json={
                "owner": "alice",
                "account": "brokerage",
                "date": "2024-02-15",
                "type": "sell",
                "ticker": "AAA",
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["warnings"] == []
