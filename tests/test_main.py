import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.common import data_loader
from backend import config as backend_config
from backend.local_api.main import app


@pytest.fixture
def client():
    os.environ["TESTING"] = "1"
    previous = backend_config.offline_mode
    backend_config.offline_mode = True
    client = TestClient(app)
    response = client.post("/token", data={"username": "testuser", "password": "password"})
    payload = response.json()
    assert response.status_code == 200, payload
    token = payload["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    try:
        yield client
    finally:
        backend_config.offline_mode = previous

# Shared mock data
mock_owners = [
    {"owner": "demo", "full_name": "Demo", "accounts": ["isa"]},
    {"owner": "alex", "full_name": "Alex Example", "accounts": ["isa", "sipp"]},
    {"owner": "joe", "full_name": "Joe Example", "accounts": ["isa", "sipp"]},
    {
        "owner": "lucy",
        "full_name": "Lucy Example",
        "accounts": ["isa"],
    },
    {"owner": "steve", "full_name": "Steve Example", "accounts": ["isa", "jpm", "sipp"]},
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
    with patch("backend.common.group_portfolio.build_group_portfolio", return_value={"slug": "testslug"}) as p:
        yield p


# Tests
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_owners(client, mock_list_plots):
    response = client.get("/owners")
    assert response.status_code == 200
    payload = response.json()
    expected = {entry["owner"]: entry for entry in mock_list_plots.return_value}

    assert {entry["owner"] for entry in payload} == set(expected)

    accounts_root = getattr(client.app.state, "accounts_root", None)
    accounts_root = Path(accounts_root) if accounts_root else None

    for entry in payload:
        owner = entry["owner"]
        expected_entry = expected[owner]
        assert entry["full_name"] == expected_entry["full_name"]

        actual_accounts = set(entry.get("accounts", []))
        provided_accounts = set(expected_entry.get("accounts", []))
        extras = actual_accounts - provided_accounts

        if not extras:
            continue

        if accounts_root is None:
            pytest.fail(
                f"Unexpected synthetic accounts {sorted(extras)} for owner '{owner}'"
            )

        owner_dir = accounts_root / owner
        for account in extras:
            assert (owner_dir / f"{account}.json").exists(), (
                f"Unexpected synthetic account '{account}' for owner '{owner}'"
            )


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
    assert response.json() == {"slug": "testslug"}


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

    def loader(owner, account, data_root=None):
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


def test_get_account_demo_fallback(client, monkeypatch):
    expected = data_loader.load_account("demo", "isa", data_loader.resolve_paths(None, None).accounts_root)

    monkeypatch.setenv("DATA_ROOT", ".")
    monkeypatch.setattr(client.app.state, "accounts_root", Path("."))

    response = client.get("/account/demo/isa")
    assert response.status_code == 200
    assert response.json() == expected


@patch(
    "backend.common.data_loader.load_account",
    side_effect=data_loader.ProviderUnavailable("s3 unavailable"),
)
def test_get_account_provider_unavailable(mock_load_account, client):
    response = client.get("/account/steve/ISA")

    assert response.status_code == 503
    assert response.json() == {"detail": "Account data provider unavailable"}


@patch(
    "backend.common.data_loader.load_account",
    side_effect=data_loader.InvalidPayload("invalid payload"),
)
def test_get_account_invalid_payload(mock_load_account, client):
    response = client.get("/account/steve/ISA")

    assert response.status_code == 502
    assert response.json() == {"detail": "Account data payload is invalid"}


@patch("backend.common.prices.refresh_prices", return_value={"updated": 5})
def test_prices_refresh(mock_refresh, client):
    response = client.post("/prices/refresh")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "updated": 5}


@patch("backend.common.prices.refresh_prices", return_value={"updated": 3})
def test_prices_refresh_get(mock_refresh, client):
    response = client.get("/prices/refresh")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "updated": 3}


def test_openapi_no_duplicate_operation_ids():
    """Regression test: all OpenAPI operation IDs must be unique (issue #2809)."""
    import warnings
    from backend.app import create_app

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        local_app = create_app()
        schema = local_app.openapi()

    duplicate_warnings = [str(w.message) for w in caught if "Duplicate Operation ID" in str(w.message)]
    assert not duplicate_warnings, f"Duplicate operation IDs found: {duplicate_warnings}"

    operation_ids = []
    for methods in schema.get("paths", {}).values():
        for op in methods.values():
            if isinstance(op, dict) and "operationId" in op:
                operation_ids.append(op["operationId"])

    refresh_ops = {schema["paths"]["/prices/refresh"][m]["operationId"] for m in ("get", "post")}
    assert refresh_ops == {"refresh_prices_get", "refresh_prices_post"}
    assert len(operation_ids) == len(set(operation_ids)), "Found duplicate operationIds in OpenAPI schema"


@patch("backend.common.portfolio_utils.aggregate_by_ticker", return_value=[{"ticker": "ABC"}])
@patch("backend.common.group_portfolio.build_group_portfolio", return_value={"slug": "testslug"})
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
@patch("backend.common.group_portfolio.build_group_portfolio", return_value={"slug": "testslug"})
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
