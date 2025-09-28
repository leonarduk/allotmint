import json
from importlib import reload
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import config
import backend.common.prices as prices
from backend.common import portfolio_utils
import backend.app as app_mod


@pytest.fixture(scope="session")
def client():
    """Create a test client with network-heavy operations stubbed."""
    config.skip_snapshot_warm = True
    config.offline_mode = True
    config.disable_auth = True
    prices.refresh_prices = lambda: {}
    portfolio_utils.list_all_unique_tickers = lambda *a, **k: []
    reload(app_mod)
    app = app_mod.create_app()
    with TestClient(app) as c:
        yield c


def sample_accounts():
    root = Path(
        config.accounts_root
        or (Path(__file__).resolve().parents[1] / "data" / "accounts")
    )
    if not root.exists():
        pytest.skip("accounts sample data unavailable", allow_module_level=True)
    metadata_stems = {
        "person",
        "config",
        "notes",
        "settings",
        "approvals",
        "approval_requests",
    }
    for owner_dir in root.iterdir():
        if owner_dir.is_dir():
            files = list(owner_dir.glob("*.json"))
            accounts = []
            for p in files:
                stem = p.stem
                lower = stem.lower()
                if lower in metadata_stems:
                    continue
                if lower.endswith("_transactions"):
                    continue
                accounts.append(stem)
            yield owner_dir.name, accounts


def test_owners_endpoint_matches_sample_data(client):
    resp = client.get("/owners")
    assert resp.status_code == 200
    owners = {o["owner"]: set(o["accounts"]) for o in resp.json()}
    assert "demo" in owners
    for owner, accounts in sample_accounts():
        assert owner in owners
        assert owners[owner] == set(accounts)


@pytest.mark.parametrize("owner,accounts", list(sample_accounts()))
def test_account_route_returns_data(client, owner, accounts):
    for acct in accounts:
        resp = client.get(f"/account/{owner}/{acct}")
        assert resp.status_code == 200
        data = resp.json()
        if "owner" in data:
            assert data["owner"].lower() == owner.lower()
        assert data["account_type"].lower() == acct.lower()
        assert isinstance(data.get("holdings"), list)


def test_account_route_adds_missing_account_type(tmp_path):
    config.skip_snapshot_warm = True
    config.offline_mode = True
    config.disable_auth = True
    prices.refresh_prices = lambda: {}
    portfolio_utils.list_all_unique_tickers = lambda *a, **k: []

    owner = "temp"
    acct = "missing"
    acct_dir = tmp_path / owner
    acct_dir.mkdir()
    (acct_dir / f"{acct}.json").write_text(
        json.dumps({"currency": "GBP", "holdings": []})
    )

    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    (demo_dir / "demo.json").write_text(
        json.dumps({"currency": "GBP", "holdings": []})
    )

    old_root = config.accounts_root
    config.accounts_root = tmp_path
    reload(app_mod)
    app = app_mod.create_app()
    with TestClient(app) as c:
        resp = c.get(f"/account/{owner}/{acct}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["account_type"] == acct
        assert "owner" not in data
        owners_resp = c.get("/owners")
        assert owners_resp.status_code == 200
        owners = owners_resp.json()
        assert any(o.get("owner") == "demo" for o in owners)
    config.accounts_root = old_root
    reload(app_mod)
