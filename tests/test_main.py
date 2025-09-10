from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.local_api.main import app


@pytest.fixture
def client():
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

# Shared mock data
mock_owners = [
    {"owner": "demo", "accounts": ["isa"]},
    {"owner": "alex", "accounts": ["isa", "sipp"]},
    {"owner": "joe", "accounts": ["isa", "sipp"]},
    {"owner": "lucy", "accounts": ["isa", "pension-forecast"]},
    {"owner": "steve", "accounts": ["isa", "jpm", "sipp"]},
]

mock_groups = [
    {"slug": "children", "name": "Children", "members": ["alex", "joe"]},
    {"slug": "adults", "name": "Adults", "members": ["lucy", "steve"]},
    {"slug": "all", "name": "All", "members": ["alex", "joe", "lucy", "steve", "demo"]},
    {"slug": "testslug", "name": "Test Group", "members": ["testuser"]},
]


# Fixtures
@pytest.fixture
def mock_list_plots():
    with patch("backend.common.data_loader.list_plots", return_value=mock_owners) as p:
        yield p


@pytest.fixture
def mock_list_groups():
    with patch("backend.common.group_portfolio.list_groups", return_value=mock_groups) as p:
        yield p


@pytest.fixture
def mock_owner_portfolio():
    with patch("backend.common.portfolio.build_owner_portfolio", return_value={"owner": "steve"}) as p:
        yield p


@pytest.fixture
def mock_group_portfolio():
    with patch("backend.common.group_portfolio.build_group_portfolio", return_value={"group": "testslug"}) as p:
        yield p


# Tests
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_owners(client, mock_list_plots):
    response = client.get("/owners")
    assert response.status_code == 200
    assert response.json() == mock_list_plots.return_value


def test_groups(client, mock_list_groups):
    response = client.get("/groups")
    assert response.status_code == 200
    assert response.json() == mock_list_groups.return_value


def test_portfolio(client, mock_owner_portfolio):
    response = client.get("/portfolio/steve")
    assert response.status_code == 200
    assert response.json() == {"owner": "steve"}


def test_portfolio_group(client, mock_group_portfolio):
    response = client.get("/portfolio-group/children")
    assert response.status_code == 200
    assert response.json() == {"group": "testslug"}


@patch("backend.common.data_loader.load_account", return_value={"account": "ISA"})
def test_get_account_no_holdings(mock_load_account, client):
    response = client.get("/account/steve/ISA")
    assert response.status_code == 200
    assert response.json() == {
        "account": "ISA",
        "account_type": "ISA",
        "holdings": [],
    }


@patch(
    "backend.common.data_loader.load_account",
    return_value={"account": "ISA", "account_type": "test"},
)
def test_get_account_preserves_type(mock_load_account, client):
    response = client.get("/account/steve/ISA")
    assert response.status_code == 200
    assert response.json() == {
        "account": "ISA",
        "account_type": "test",
        "holdings": [],
    }


@patch(
    "backend.common.data_loader.load_account",
    return_value={"account": "ISA", "approvals": ["H"]},
)
def test_get_account_with_holdings(mock_load_account, client):
    response = client.get("/account/steve/ISA")
    assert response.status_code == 200
    data = response.json()
    assert data == {"account": "ISA", "account_type": "ISA", "holdings": ["H"]}
    assert "approvals" not in data


@patch("backend.common.data_loader.resolve_paths")
@patch("backend.common.data_loader.load_account")
def test_get_account_case_insensitive(mock_load_account, mock_resolve, client, tmp_path):
    (tmp_path / "steve").mkdir()
    (tmp_path / "steve" / "isa.json").write_text("{}", encoding="utf-8")

    def loader(owner, account):
        if loader.calls == 0:
            loader.calls += 1
            raise FileNotFoundError
        return {"account": account}

    loader.calls = 0
    mock_load_account.side_effect = loader
    mock_resolve.return_value = SimpleNamespace(accounts_root=tmp_path)

    resp = client.get("/account/steve/ISA")
    assert resp.status_code == 200
    assert resp.json() == {"account": "isa", "account_type": "isa", "holdings": []}


@patch("backend.common.prices.refresh_prices", return_value={"updated": 5})
def test_prices_refresh(mock_refresh, client):
    response = client.post("/prices/refresh")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "updated": 5}


@patch("backend.common.portfolio_utils.aggregate_by_ticker", return_value=[{"ticker": "ABC"}])
@patch("backend.common.group_portfolio.build_group_portfolio", return_value={"group": "testslug"})
@patch("backend.common.group_portfolio.list_groups", return_value=mock_groups)
def test_group_by_instrument(mock_groups, mock_build, mock_aggregate, client):
    response = client.get("/portfolio-group/testslug/instruments")
    assert response.status_code == 200
    assert response.json() == [{"ticker": "ABC"}]


@patch(
    "backend.common.instrument_api.timeseries_for_ticker",
    return_value={"prices": [{"date": "2025-01-01"}], "mini": {"7": [], "30": [], "180": []}},
)
@patch("backend.common.instrument_api.positions_for_ticker", return_value=[{"ticker": "ABC"}])
@patch("backend.common.group_portfolio.list_groups", return_value=mock_groups)
@patch("backend.common.group_portfolio.build_group_portfolio", return_value={"group": "testslug"})
def test_instrument_detail(mock_list, mock_build, mock_positions, mock_timeseries, client):
    response = client.get("/portfolio-group/testslug/instrument/ABC")
    assert response.status_code == 200
    payload = response.json()
    assert "prices" in payload
    assert "mini" in payload
    assert "positions" in payload


@patch("backend.routes.portfolio.portfolio_mod.list_owners", return_value=["steve"])
@patch("backend.common.risk.compute_sharpe_ratio", return_value=1.23)
@patch("backend.common.risk.compute_portfolio_var", return_value={"1d": 100.0, "10d": 200.0})
def test_var_endpoint(mock_var, mock_sharpe, mock_list, client):
    response = client.get("/var/steve")
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"] == "steve"
    assert payload["var"] == {"1d": 100.0, "10d": 200.0}
    assert payload["sharpe_ratio"] == 1.23


@patch("backend.routes.portfolio.portfolio_mod.list_owners", return_value=["steve"])
@patch("backend.common.risk.compute_sharpe_ratio", side_effect=FileNotFoundError)
@patch("backend.common.risk.compute_portfolio_var", side_effect=FileNotFoundError)
def test_var_owner_not_found(mock_var, mock_sharpe, mock_list, client):
    response = client.get("/var/missing")
    assert response.status_code == 404


@patch("backend.routes.portfolio.portfolio_mod.list_owners", return_value=["steve"])
@patch("backend.common.risk.compute_sharpe_ratio", return_value=1.0)
@patch("backend.common.risk.compute_portfolio_var", side_effect=ValueError("bad"))
def test_var_invalid_params(mock_var, mock_sharpe, mock_list, client):
    response = client.get("/var/steve?confidence=2")
    assert response.status_code == 400


@patch("backend.routes.portfolio.portfolio_mod.list_owners", return_value=["steve"])
def test_var_invalid_confidence_range(mock_list, client):
    response = client.get("/var/steve?confidence=101")
    assert response.status_code == 400


@patch("backend.timeseries.fetch_timeseries.fetch_yahoo_timeseries")
@patch("backend.utils.html_render.render_timeseries_html", return_value="<html>OK</html>")
def test_get_timeseries_html(mock_render, mock_fetch, client):
    mock_df = MagicMock()
    mock_df.empty = False
    mock_fetch.return_value = mock_df
    response = client.get("/timeseries/html?ticker=ABC&period=1y&interval=1d")
    assert response.status_code == 200
    assert "<html>" in response.text
