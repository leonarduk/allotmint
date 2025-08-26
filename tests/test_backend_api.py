import pytest
from fastapi.testclient import TestClient

from backend.local_api.main import app
from backend.common.instruments import get_instrument_meta
import backend.common.alerts as alerts

client = TestClient(app)
token = client.post(
    "/token", data={"username": "testuser", "password": "password"}
).json()["access_token"]
client.headers.update({"Authorization": f"Bearer {token}"})

# allow alerts to operate without SNS configuration
alerts.config.sns_topic_arn = None


@pytest.fixture
def stub_group_portfolio(monkeypatch):
    """Return a minimal group portfolio to avoid heavy enrichment."""

    def _build(slug: str):
        return {
            "slug": slug,
            "accounts": [
                {
                    "name": "stub",
                    "value_estimate_gbp": 100.0,
                    "holdings": [
                        {
                            "ticker": "STUB",
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


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data and data["status"] == "ok"
    assert "env" in data


def test_owners():
    resp = client.get("/owners")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_groups():
    resp = client.get("/groups")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_valid_group_portfolio(stub_group_portfolio):
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


def test_invalid_group_portfolio():
    resp = client.get("/portfolio-group/doesnotexist")
    assert resp.status_code == 404


def test_valid_portfolio():
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    first_name = groups[0]["members"][0]
    resp = client.get(f"/portfolio/{first_name}")
    assert resp.status_code == 200


def test_invalid_portfolio():
    resp = client.get("/portfolio/noone")
    assert resp.status_code == 404


def test_valid_account():
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    first_name = groups[0]["members"][0]
    # You'll need to replace with a valid account name like "ISA" or "SIPP"
    resp = client.get(f"/account/{first_name}/ISA")
    assert resp.status_code == 200


def test_invalid_account():
    resp = client.get("/account/noone/noacct")
    assert resp.status_code == 404


def test_prices_refresh(mock_refresh_prices):
    resp = client.post("/prices/refresh")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_group_instruments():
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


def test_transactions_endpoint():
    resp = client.get("/transactions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_compliance_endpoint():
    owners = client.get("/owners").json()
    assert owners, "No owners returned"
    owner = owners[0]["owner"]
    resp = client.get(f"/compliance/{owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner"].lower() == owner.lower()
    assert "warnings" in data and isinstance(data["warnings"], list)


def test_compliance_invalid_owner():
    resp = client.get("/compliance/noone")
    assert resp.status_code == 404


def test_instrument_detail_valid():
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


def test_instrument_detail_not_found():
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}/instrument/FAKETICK")
    assert resp.status_code == 404


def test_yahoo_timeseries_html():
    ticker = "AAPL"
    resp = client.get(f"/timeseries/html?ticker={ticker}&period=1y&interval=1d")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "<html" in html and "<table" in html
    assert ticker.lower() in html


def test_alerts_endpoint(mock_refresh_prices, monkeypatch):
    alerts._RECENT_ALERTS.clear()
    monkeypatch.setattr(alerts, "publish_alert", lambda alert: alerts._RECENT_ALERTS.append(alert))
    client.post("/prices/refresh")
    resp = client.get("/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# @pytest.mark.parametrize("format", ["html", "json", "csv"])
# def test_ft_timeseries(format):
#     ticker = "GB00B45Q9038:GBP"
#     resp = client.get(f"/timeseries/ft?ticker={ticker}&period=1y&interval=1d&format={format}")
#     if resp.status_code == 404:
#         pytest.skip("FT timeseries data not available")
#
#     assert resp.status_code == 200
#
#     if format == "json":
#         data = resp.json()
#         validate_timeseries(data)
#
#     elif format == "csv":
#         df = pd.read_csv(StringIO(resp.text))
#         assert not df.empty
#         assert "date" in df.columns and "close" in df.columns
#         assert df["date"].is_monotonic_increasing
#
#     elif format == "html":
#         html = resp.text.lower()
#         assert "<table" in html and "ft time series" in html

def test_screener_endpoint(monkeypatch):
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

def test_var_endpoint_default():
    owners = client.get("/owners").json()
    assert owners, "No owners returned"
    owner = owners[0]["owner"]
    resp = client.get(f"/var/{owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert "var" in data and isinstance(data["var"], dict)


@pytest.mark.parametrize("days,confidence", [(10, 0.9), (30, 0.99)])
def test_var_endpoint_params(days, confidence):
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
