import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.local_api.main import app

client = TestClient(app)

# Shared mock data
mock_owners = [
    {"owner": "alex", "accounts": ["isa", "sipp"]},
    {"owner": "joe", "accounts": ["isa", "sipp"]},
    {"owner": "lucy", "accounts": ["isa", "pension-forecast"]},
    {"owner": "steve", "accounts": ["isa", "jpm", "sipp"]},
]

mock_groups = [
    {"slug": "children", "name": "Children", "members": ["alex", "joe"]},
    {"slug": "adults", "name": "Adults", "members": ["lucy", "steve"]},
    {"slug": "all", "name": "All", "members": ["alex", "joe", "lucy", "steve"]},
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
def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_owners(mock_list_plots):
    response = client.get("/owners")
    assert response.status_code == 200
    assert response.json() == mock_list_plots.return_value

def test_groups(mock_list_groups):
    response = client.get("/groups")
    assert response.status_code == 200
    assert response.json() == mock_list_groups.return_value

def test_portfolio(mock_owner_portfolio):
    response = client.get("/portfolio/steve")
    assert response.status_code == 200
    assert response.json() == {"owner": "steve"}

def test_portfolio_group(mock_group_portfolio):
    response = client.get("/portfolio-group/children")
    assert response.status_code == 200
    assert response.json() == {"group": "testslug"}

@patch("backend.common.data_loader.load_account", return_value={"account": "ISA"})
def test_get_account(mock_load_account):
    response = client.get("/account/steve/ISA")
    assert response.status_code == 200
    assert response.json() == {"account": "ISA"}

@patch("backend.common.prices.refresh_prices", return_value={"updated": 5})
def test_prices_refresh(mock_refresh):
    response = client.post("/prices/refresh")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "updated": 5}

@patch("backend.common.portfolio_utils.aggregate_by_ticker", return_value=[{"ticker": "ABC"}])
@patch("backend.common.group_portfolio.build_group_portfolio", return_value={"group": "testslug"})
@patch("backend.common.group_portfolio.list_groups", return_value=mock_groups)
def test_group_by_instrument(mock_groups, mock_build, mock_aggregate):
    response = client.get("/portfolio-group/testslug/instruments")
    assert response.status_code == 200
    assert response.json() == [{"ticker": "ABC"}]

@patch("backend.common.instrument_api.timeseries_for_ticker", return_value=[{"date": "2025-01-01"}])
@patch("backend.common.instrument_api.positions_for_ticker", return_value=[{"ticker": "ABC"}])
@patch("backend.common.group_portfolio.list_groups", return_value=mock_groups)
@patch("backend.common.group_portfolio.build_group_portfolio", return_value={"group": "testslug"})
def test_instrument_detail(mock_list, mock_build, mock_positions, mock_timeseries):
    response = client.get("/portfolio-group/testslug/instrument/ABC")
    assert response.status_code == 200
    assert "prices" in response.json()
    assert "positions" in response.json()

@patch("backend.timeseries.fetch_timeseries.fetch_yahoo_timeseries")
@patch("backend.utils.html_render.render_timeseries_html", return_value="<html>OK</html>")
def test_get_timeseries_html(mock_render, mock_fetch):
    mock_df = MagicMock()
    mock_df.empty = False
    mock_fetch.return_value = mock_df
    response = client.get("/timeseries/html?ticker=ABC&period=1y&interval=1d")
    assert response.status_code == 200
    assert "<html>" in response.text
