from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import portfolio


def _client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(portfolio.router)
    app.state.accounts_root = tmp_path
    return TestClient(app)


def test_portfolio_success(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: {"owner": owner},
    )
    resp = client.get("/portfolio/alice")
    assert resp.status_code == 200
    assert resp.json()["owner"] == "alice"


def test_portfolio_not_found(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: (_ for _ in ()).throw(FileNotFoundError()),
    )
    resp = client.get("/portfolio/bob")
    assert resp.status_code == 404


def test_portfolio_sectors(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    sample_portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA",
                        "sector": "Tech",
                        "market_value_gbp": 150,
                        "cost_gbp": 100,
                        "gain_gbp": 50,
                    },
                    {
                        "ticker": "BBB",
                        "sector": "Finance",
                        "market_value_gbp": 220,
                        "cost_gbp": 200,
                        "gain_gbp": 20,
                    },
                ]
            }
        ],
    }

    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: sample_portfolio,
    )

    resp = client.get("/portfolio/alice/sectors")
    assert resp.status_code == 200
    sectors = {row["sector"]: row for row in resp.json()}
    assert sectors["Tech"]["market_value_gbp"] == 150
    assert sectors["Finance"]["gain_gbp"] == 20


def test_portfolio_var(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.risk.compute_portfolio_var",
        lambda owner, days, confidence, include_cash: {"1d": 1.0},
    )
    monkeypatch.setattr(
        "backend.routes.portfolio.risk.compute_sharpe_ratio",
        lambda owner, days: 0.5,
    )
    resp = client.get("/var/alice", params={"days": 10, "confidence": 0.9})
    assert resp.status_code == 200
    data = resp.json()
    assert data["var"] == {"1d": 1.0}
    assert data["sharpe_ratio"] == 0.5


def test_portfolio_var_owner_missing(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.risk.compute_portfolio_var",
        lambda owner, days=365, confidence=0.95, include_cash=True: (_ for _ in ()).throw(FileNotFoundError()),
    )
    resp = client.get("/var/alice")
    assert resp.status_code == 404


def test_portfolio_var_bad_params(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    def _raise(owner, days, confidence, include_cash):
        raise ValueError("bad")

    monkeypatch.setattr("backend.routes.portfolio.risk.compute_portfolio_var", _raise)
    resp = client.get("/var/alice")
    assert resp.status_code == 400
