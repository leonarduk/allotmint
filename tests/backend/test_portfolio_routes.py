import json

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
        lambda owner, days=365, confidence=0.95, include_cash=True: (_ for _ in ()).throw(
            FileNotFoundError()
        ),
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


# ---------------------------------------------------------------------------
# Path traversal — /account/{owner}/{account}
# ---------------------------------------------------------------------------


def test_account_percent_encoded_slash_owner_returns_404(monkeypatch, tmp_path):
    """A %2F-encoded slash in the owner segment returns 404.

    When '%2F' is decoded by the HTTP layer the path becomes
    '/account/../evil/isa', which routers normalise to '/account/evil/isa'.
    This returns 404 because no such owner exists — the traversal is blocked
    at the URL-normalisation layer, *before* safe_join is reached.

    The safe_join guard for a decoded '../evil' owner is verified directly in
    tests/backend/routes/test_accounts_helpers.py::
        test_resolve_owner_directory_dotdot_returns_none
    and in tests/backend/common/test_data_loader.py::
        test_load_account_dotdot_owner_raises_missing_data.
    """
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/account/..%2Fevil/isa")
    assert resp.status_code == 404


def test_account_case_insensitive_owner_and_account_loads_matched_directory(monkeypatch, tmp_path):
    """Owner/account casing mismatches should load the on-disk match."""
    owner_dir = tmp_path / "Alice"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text(
        json.dumps({"account_type": "ISA", "holdings": [{"ticker": "ABC"}]}),
        encoding="utf-8",
    )
    client = _client(monkeypatch, tmp_path)

    resp = client.get("/account/alice/ISA")

    assert resp.status_code == 200
    assert resp.json()["account_type"] == "ISA"
    assert resp.json()["holdings"] == [{"ticker": "ABC"}]


def test_account_valid_missing_returns_404(monkeypatch, tmp_path):
    """Non-existent but valid owner/account yields 404, not 500."""
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/account/noowner/noaccount")
    assert resp.status_code == 404
