import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.common.instruments import get_instrument_meta
import backend.common.alerts as alerts
from backend import config as backend_config


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with offline mode enabled."""
    previous = backend_config.config.offline_mode
    backend_config.config.offline_mode = True
    from backend.local_api.main import app

    client = TestClient(app)
    token = client.post(
        "/token", data={"username": "testuser", "password": "password"}
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    # allow alerts to operate without SNS configuration
    alerts.config.sns_topic_arn = None
    try:
        yield client
    finally:
        backend_config.config.offline_mode = previous


@pytest.fixture(autouse=True)
def mock_group_portfolio(monkeypatch):
    """Provide a lightweight group portfolio for known slugs."""

    def _build(slug: str):
        if slug == "doesnotexist":
            raise HTTPException(status_code=404, detail="Group not found")
        return {
            "slug": slug,
            "accounts": [
                {
                    "name": "stub",
                    "value_estimate_gbp": 100.0,
                    "holdings": [
                        {
                            "ticker": "STUB",
                            "name": "Stub Corp",
                            "units": 1.0,
                            "market_value_gbp": 100.0,
                            "gain_gbp": 10.0,
                            "cost_basis_gbp": 90.0,
                            "day_change_gbp": 1.0,
                        }
                    ],
                }
            ],
            "total_value_estimate_gbp": 100.0,
        }

    monkeypatch.setattr(
        "backend.common.group_portfolio.build_group_portfolio", _build
    )


@pytest.fixture
def mock_refresh_prices(monkeypatch):
    """Stub out refresh_prices to avoid expensive operations."""

    def _refresh() -> dict:
        return {"tickers": [], "snapshot": {}, "timestamp": "stub"}

    monkeypatch.setattr("backend.common.prices.refresh_prices", _refresh)


@pytest.fixture
def mock_timeseries_for_ticker(monkeypatch):
    """Provide a small static timeseries for any ticker except FAKETICK."""

    def _fake_timeseries(ticker: str, days: int = 365):
        if ticker == "FAKETICK":
            return {"prices": [], "mini": {"7": [], "30": [], "180": []}}
        prices = [
            {"date": "2024-01-01", "close": 1.0},
            {"date": "2024-01-02", "close": 1.1},
        ]
        mini = {"7": prices[-7:], "30": prices[-30:], "180": prices[-180:]}
        return {"prices": prices, "mini": mini}

    monkeypatch.setattr(
        "backend.common.instrument_api.timeseries_for_ticker", _fake_timeseries
    )


@pytest.fixture
def mock_positions_for_ticker(monkeypatch):
    """Return a minimal positions list for any ticker."""

    def _fake_positions(group_slug: str, ticker: str):
        return [{"gain_pct": 0.0}]

    monkeypatch.setattr(
        "backend.common.instrument_api.positions_for_ticker", _fake_positions
    )


def validate_timeseries(prices):
    assert isinstance(prices, list)
    assert len(prices) > 0
    first = prices[0]
    assert "date" in first
    # Price data may be provided in different currencies, e.g. "close_gbp"
    price_keys = [key for key in first.keys() if key.startswith("close")]
    assert price_keys, "No price field starting with 'close' found"
    assert "date" in first and ("close" in first or "close_gbp" in first)
    dates = [p["date"] for p in prices]
    assert dates == sorted(dates), "Dates are not in ascending order"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data and data["status"] == "ok"
    assert "env" in data


def test_owners(client):
    resp = client.get("/owners")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_groups(client):
    resp = client.get("/groups")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_valid_group_portfolio(client):
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    group_slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{group_slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert "slug" in data and data["slug"] == group_slug
    assert "accounts" in data and isinstance(data["accounts"], list)
    assert data["accounts"], "Accounts list should not be empty"
    assert "total_value_estimate_gbp" in data
    assert data["total_value_estimate_gbp"] > 0
    first_acct = data["accounts"][0]
    assert "value_estimate_gbp" in first_acct
    first_holding = first_acct["holdings"][0]
    assert "day_change_gbp" in first_holding


def test_invalid_group_portfolio(client):
    resp = client.get("/portfolio-group/doesnotexist")
    assert resp.status_code == 404


def test_valid_portfolio(client):
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    first_name = groups[0]["members"][0]
    resp = client.get(f"/portfolio/{first_name}")
    assert resp.status_code == 200


def test_invalid_portfolio(client):
    resp = client.get("/portfolio/noone")
    assert resp.status_code == 404


def test_valid_account(client):
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    first_name = groups[0]["members"][0]
    # You'll need to replace with a valid account name like "ISA" or "SIPP"
    resp = client.get(f"/account/{first_name}/ISA")
    assert resp.status_code == 200


def test_invalid_account(client):
    resp = client.get("/account/noone/noacct")
    assert resp.status_code == 404


def test_prices_refresh(client):
    resp = client.post("/prices/refresh")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_group_instruments(client):
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}/instruments")
    assert resp.status_code == 200
    instruments = resp.json()
    assert isinstance(instruments, list)
    assert len(instruments) > 0
    assert "ticker" in instruments[0]
    assert "gain_pct" in instruments[0]
    # At least one instrument should have a market value once holdings are
    # aggregated, even if no explicit price snapshot exists.
    assert any((inst.get("market_value_gbp") or 0) > 0 for inst in instruments)

    # if metadata contains a name, it should be reflected in the API output
    for inst in instruments:
        meta = get_instrument_meta(inst["ticker"])
        if meta.get("name"):
            assert inst["name"] == meta["name"]


def test_transactions_endpoint(client):
    resp = client.get("/transactions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_compliance_endpoint(client):
    owners = client.get("/owners").json()
    assert owners, "No owners returned"
    owner = owners[0]["owner"]
    resp = client.get(f"/compliance/{owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner"].lower() == owner.lower()
    assert "warnings" in data and isinstance(data["warnings"], list)


def test_compliance_invalid_owner(client):
    resp = client.get("/compliance/noone")
    assert resp.status_code == 404


def test_instrument_detail_valid(client):
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    instruments = client.get(f"/portfolio-group/{slug}/instruments").json()
    if not instruments:
        pytest.skip("No instruments available for this group")

    for inst in instruments:
        ticker = inst["ticker"]
        resp = client.get(f"/portfolio-group/{slug}/instrument/{ticker}")
        if resp.status_code == 200:
            json = resp.json()
            assert "prices" in json and isinstance(json["prices"], list)
            assert "positions" in json and isinstance(json["positions"], list)
            if json["positions"]:
                assert "gain_pct" in json["positions"][0]
            validate_timeseries(json["prices"])
            return
    pytest.skip("No instrument with available price data")


def test_instrument_detail_not_found(client):
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}/instrument/FAKETICK")
    assert resp.status_code == 404


def test_yahoo_timeseries_html(client):
    ticker = "AAPL"
    resp = client.get(f"/timeseries/html?ticker={ticker}&period=1y&interval=1d")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "<html" in html and "<table" in html
    assert ticker.lower() in html


def test_alerts_endpoint(client, monkeypatch):
    alerts._RECENT_ALERTS.clear()
    alerts.clear_state()
    monkeypatch.setattr(alerts, "publish_alert", lambda alert: alerts._RECENT_ALERTS.append(alert))
    client.post("/prices/refresh")
    resp = client.get("/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_screener_endpoint(client, monkeypatch):
    from backend.screener import Fundamentals

    def mock_fetch(ticker: str) -> Fundamentals:
        if ticker == "AAA":
            return Fundamentals(ticker="AAA", peg_ratio=0.5, roe=0.2)
        return Fundamentals(ticker="BBB", peg_ratio=2.0, roe=0.1)

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    resp = client.get("/screener?tickers=AAA,BBB&peg_max=1&roe_min=0.15")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "AAA"


def test_var_endpoint_default(client):
    if backend_config.config.offline_mode:
        pytest.skip("VaR endpoint requires data unavailable in offline mode")
    owners = client.get("/owners").json()
    assert owners, "No owners returned"
    owner = owners[0]["owner"]
    resp = client.get(f"/var/{owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert "var" in data and isinstance(data["var"], dict)


@pytest.mark.parametrize("days,confidence", [(10, 0.9), (30, 0.99)])
def test_var_endpoint_params(client, days, confidence):
    if backend_config.config.offline_mode:
        pytest.skip("VaR endpoint requires data unavailable in offline mode")
    owners = client.get("/owners").json()
    assert owners, "No owners returned"
    owner = owners[0]["owner"]
    resp = client.get(f"/var/{owner}?days={days}&confidence={confidence}")
    assert resp.status_code == 200
    data = resp.json()
    assert "var" in data
    var = data["var"]
    assert var.get("window_days") == days
    assert var.get("confidence") == confidence
