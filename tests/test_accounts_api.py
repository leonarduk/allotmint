import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
import backend.common.prices as prices
from backend.common import portfolio_utils


@pytest.fixture(scope="session")
def client():
    """Create a test client with network-heavy operations stubbed."""
    config.skip_snapshot_warm = True
    config.offline_mode = True
    prices.refresh_prices = lambda: {}
    portfolio_utils.list_all_unique_tickers = lambda *a, **k: []
    app = create_app()
    with TestClient(app) as c:
        yield c


def sample_accounts():
    root = Path(__file__).resolve().parents[1] / "data" / "accounts"
    for owner_dir in root.iterdir():
        if owner_dir.is_dir():
            accounts = [p.stem for p in owner_dir.glob("*.json") if p.stem != "person"]
            yield owner_dir.name, accounts


def test_owners_endpoint_matches_sample_data(client):
    resp = client.get("/owners")
    assert resp.status_code == 200
    owners = {o["owner"]: set(o["accounts"]) for o in resp.json()}
    for owner, accounts in sample_accounts():
        assert owner in owners
        assert set(accounts).issubset(owners[owner])


@pytest.mark.parametrize("owner,accounts", list(sample_accounts()))
def test_account_route_returns_data(client, owner, accounts):
    for acct in accounts:
        resp = client.get(f"/account/{owner}/{acct}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["owner"].lower() == owner.lower()
        assert data["account_type"].lower() == acct.lower()
        assert isinstance(data.get("holdings"), list)


def test_account_route_adds_missing_account_type(tmp_path):
    config.skip_snapshot_warm = True
    config.offline_mode = True
    prices.refresh_prices = lambda: {}
    portfolio_utils.list_all_unique_tickers = lambda *a, **k: []

    owner = "temp"
    acct = "missing"
    acct_dir = tmp_path / owner
    acct_dir.mkdir()
    (acct_dir / f"{acct}.json").write_text(
        json.dumps({"owner": owner, "currency": "GBP", "holdings": []})
    )

    old_root = config.accounts_root
    config.accounts_root = tmp_path
    app = create_app()
    with TestClient(app) as c:
        resp = c.get(f"/account/{owner}/{acct}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["account_type"] == acct
    config.accounts_root = old_root
