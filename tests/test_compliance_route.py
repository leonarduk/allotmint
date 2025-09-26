import json
from datetime import date
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import compliance


def _setup_app(tmp_path):
    accounts = tmp_path / "accounts" / "alice"
    accounts.mkdir(parents=True)
    data = {
        "account_type": "brokerage",
        "transactions": [
            {"date": "2024-01-10", "ticker": "AAA", "type": "buy", "shares": 10},
            {"date": "2024-01-05", "ticker": "BBB", "type": "buy", "shares": 5},
        ],
    }
    (accounts / "alice_transactions.json").write_text(json.dumps(data))
    settings = {"hold_days_min": 10, "max_trades_per_month": 5}
    (accounts / "settings.json").write_text(json.dumps(settings))
    app = create_app()
    app.state.accounts_root = accounts.parent
    return app


def test_compliance_owner_route(tmp_path, monkeypatch):
    app = _setup_app(tmp_path)

    class FakeDate(date):
        @classmethod
        def today(cls) -> date:  # type: ignore[override]
            return date(2024, 1, 15)

    with monkeypatch.context() as m:
        m.setattr(compliance, "date", FakeDate)
        with TestClient(app) as client:
            resp = client.get("/compliance/alice")
            assert resp.status_code == 200
            data = resp.json()
            assert data["owner"] == "alice"
            assert data["warnings"] == []
            assert data["hold_countdowns"] == {"AAA": 5}
            assert data["trades_remaining"] == 3
            assert data["trades_this_month"] == 2


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


def test_validate_trade_commodity_etf_requires_approval(tmp_path, monkeypatch):
    app = _setup_app(tmp_path)
    monkeypatch.setattr(
        "backend.common.compliance.get_instrument_meta",
        lambda t: {"instrumentType": "ETF", "asset_class": "Commodity"},
    )
    monkeypatch.setattr(compliance.config, "approval_exempt_types", ["ETF"])
    with TestClient(app) as client:
        resp = client.post(
            "/compliance/validate",
            json={
                "owner": "alice",
                "account": "brokerage",
                "date": "2024-02-15",
                "type": "sell",
                "ticker": "AAA",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any("without approval" in w for w in data["warnings"])


def test_validate_trade_missing_owner(tmp_path):
    app = _setup_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/compliance/validate", json={})
        assert resp.status_code == 422


def test_validate_trade_when_owner_discovery_fails(tmp_path):
    app = _setup_app(tmp_path)
    # Point the app to a non-existent accounts directory so owner discovery
    # yields an empty set. The endpoint should still accept the request and
    # fall back to scaffolding the owner on demand instead of returning a 404.
    missing_root = tmp_path / "missing"
    app.state.accounts_root = missing_root

    with TestClient(app) as client:
        resp = client.post(
            "/compliance/validate",
            json={
                "owner": " demo ",
                "account": "brokerage",
                "date": "2024-03-01",
                "type": "buy",
                "ticker": "XYZ",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["owner"] == "demo"
        assert data["warnings"] == []
        scaffold = missing_root / "demo" / "demo_transactions.json"
        assert scaffold.exists()
